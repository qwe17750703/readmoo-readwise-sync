#!/usr/bin/env python3
"""
Readmoo → Readwise 全書同步工具
一次將 Readmoo 所有書籍的畫線同步到 Readwise。

互動模式：  python main.py
排程模式：  python main.py --silent
"""

import argparse
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.readmoo import ReadmooClient
from src.readwise import ReadwiseClient
from src.notify import notify
from src.cache import SyncCache


LOG_PATH = Path(__file__).parent / "sync.log"


def setup_logging(silent: bool) -> logging.Logger:
    logger = logging.getLogger("sync")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")

    file_handler = RotatingFileHandler(LOG_PATH, maxBytes=512 * 1024, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    if not silent:
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(console)

    return logger


def get_token(env_key: str, prompt_text: str, silent: bool, logger: logging.Logger) -> str:
    value = os.getenv(env_key, "").strip()
    if value:
        return value
    if silent:
        logger.error(f"--silent 模式下找不到環境變數 {env_key}，請填好 .env 後再試")
        notify("Readmoo 同步失敗", f"設定缺漏：未找到 {env_key}")
        sys.exit(2)
    value = input(f"{prompt_text}: ").strip()
    if not value:
        logger.error(f"未提供 {env_key}，程式結束")
        sys.exit(1)
    return value


def make_progress(silent: bool):
    if silent:
        return None  # silent 模式不畫進度條
    def progress(current: int, total: int, title: str, skipped: bool = False):
        bar_len = 30
        filled = int(bar_len * current / total)
        bar = "█" * filled + "░" * (bar_len - filled)
        tag = "略過" if skipped else "讀取"
        print(f"\r[{bar}] {current}/{total} [{tag}] {title[:35]:<35}", end="", flush=True)
    return progress


def run(silent: bool, force: bool = False) -> int:
    logger = setup_logging(silent)
    logger.info("=" * 50)
    logger.info(f"開始同步（模式：{'排程' if silent else '互動'}{'，強制全量' if force else '，增量'}）")

    readmoo_token = get_token(
        "READMOO_TOKEN",
        "請輸入 Readmoo Bearer token (取得方式見 .env.example)\nReadmoo token",
        silent, logger,
    )
    readwise_token = get_token(
        "READWISE_TOKEN",
        "請輸入 Readwise token (https://readwise.io/access_token)\nReadwise token",
        silent, logger,
    )

    readmoo = ReadmooClient(readmoo_token)
    readwise = ReadwiseClient(readwise_token)
    cache = SyncCache()
    if force:
        cache.clear()
        logger.info("已清除本機快取，將重新同步所有書籍")

    # 1. 取得書單
    logger.info("步驟 1/3：取得 Readmoo 書籍列表...")
    try:
        readings = readmoo.get_all_readings()
    except PermissionError as e:
        logger.error(f"Readmoo token 失效：{e}")
        notify(
            "Readmoo 同步失敗 — Token 已過期",
            "請重新從瀏覽器 DevTools 取得新的 Bearer token，更新到 .env",
        )
        return 3
    except Exception as e:
        logger.exception(f"取得 Readmoo 書籍時發生錯誤：{e}")
        notify("Readmoo 同步失敗", f"取得書單失敗：{type(e).__name__}")
        return 4

    logger.info(f"  共找到 {len(readings)} 本書")
    if not readings:
        logger.info("書架是空的，結束")
        return 0

    # 2. 抓畫線（用快取跳過沒變過的書）
    logger.info("步驟 2/3：取得每本書的畫線（增量）...")
    try:
        all_highlights, pending_updates, stats = readmoo.get_all_highlights(
            cache=cache,
            force=force,
            on_progress=make_progress(silent),
        )
    except PermissionError as e:
        logger.error(f"Readmoo token 失效：{e}")
        notify(
            "Readmoo 同步失敗 — Token 已過期",
            "請重新從瀏覽器 DevTools 取得新的 Bearer token，更新到 .env",
        )
        return 3
    except Exception as e:
        logger.exception(f"取得畫線時發生錯誤：{e}")
        notify("Readmoo 同步失敗", f"取得畫線失敗：{type(e).__name__}")
        return 4

    if not silent:
        print()  # progress bar 換行
    logger.info(
        f"  共 {stats['books_total']} 本書 — 略過 {stats['books_skipped']} 本，"
        f"讀取 {stats['books_fetched']} 本，新增 {stats['highlights_new']} 條畫線"
    )
    if not all_highlights:
        logger.info("沒有任何書籍有變動，不需同步")
        notify(
            "Readmoo 同步完成",
            f"全部 {stats['books_total']} 本書都沒有新畫線",
        )
        cache.commit()  # 更新 last_full_sync 時間
        return 0

    # 3. 推送 Readwise
    logger.info("步驟 3/3：寫入 Readwise...")
    try:
        result = readwise.import_highlights(all_highlights)
    except PermissionError as e:
        logger.error(f"Readwise token 失效：{e}")
        notify(
            "Readmoo 同步失敗 — Readwise Token 無效",
            "請至 https://readwise.io/access_token 重新取得",
        )
        return 3
    except Exception as e:
        logger.exception(f"寫入 Readwise 時發生錯誤：{e}")
        notify("Readmoo 同步失敗", f"寫入 Readwise 失敗：{type(e).__name__}")
        return 4

    logger.info(f"匯入 {result['imported']} / {result['total']} 條畫線")

    # 找出哪幾本書有畫線真的失敗，那幾本就不進快取，其他全部 commit
    failed_reading_ids = {
        all_highlights[i].book.reading_id
        for i in result["failed_indices"]
        if i < len(all_highlights)
    }
    if result["errors"]:
        for err in result["errors"][:10]:  # 只記前 10 條免得 log 太大
            logger.warning(
                f"  畫線 #{err['index']} HTTP {err['status']}：{err['text_preview']}... — {err['body']}"
            )
        if len(result["errors"]) > 10:
            logger.warning(f"  （另有 {len(result['errors']) - 10} 條錯誤未列出）")

    cached_count = 0
    for reading_id, info in pending_updates.items():
        if reading_id in failed_reading_ids:
            continue  # 這本書有畫線失敗 → 下次重抓
        cache.stage_book(reading_id, info["title"], info["highlight_count"])
        cached_count += 1
    cache.commit()
    logger.info(
        f"快取已更新：下次將略過 {cached_count} 本書"
        + (f"（{len(failed_reading_ids)} 本因部分畫線失敗會重試）" if failed_reading_ids else "")
    )

    if result["errors"]:
        notify(
            "Readmoo 同步完成（部分畫線失敗）",
            f"成功 {result['imported']}/{result['total']}，失敗 {len(result['errors'])} 條，下次會自動重試這幾本書",
        )
        return 5

    notify(
        "Readmoo 同步完成",
        f"略過 {stats['books_skipped']} 本、讀取 {stats['books_fetched']} 本，匯入 {result['imported']} 條畫線",
    )
    return 0


def main():
    parser = argparse.ArgumentParser(description="Readmoo → Readwise 全書畫線同步")
    parser.add_argument(
        "--silent",
        action="store_true",
        help="無互動模式（給 Windows 工作排程器用），缺 token 時直接結束並通知",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="忽略快取，強制重抓所有書的畫線（Readwise 仍會自動去重）",
    )
    args = parser.parse_args()
    sys.exit(run(args.silent, args.force))


if __name__ == "__main__":
    main()

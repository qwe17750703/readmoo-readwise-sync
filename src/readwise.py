import time
import requests
from typing import List, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from .readmoo import Highlight

READWISE_API = "https://readwise.io/api/v2"
BATCH_SIZE = 100  # Readwise recommends batching
RATE_LIMIT_PAUSE = 0.5

# Readwise 各欄位字數上限（超過會被退回整個 batch）
MAX_TEXT = 8191
MAX_TITLE = 511
MAX_AUTHOR = 1024
MAX_NOTE = 8191
MAX_SOURCE_URL = 2047


def _trunc(text: str, max_len: int) -> str:
    if not text or len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


class ReadwiseClient:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Token {token}"})

    def _verify_token(self):
        resp = self.session.get(f"{READWISE_API}/auth/")
        if resp.status_code != 204:
            raise PermissionError("Readwise token 無效，請至 https://readwise.io/access_token 取得正確的 token。")

    def _build_entry(self, h: "Highlight") -> dict:
        entry = {
            "text": _trunc(h.text, MAX_TEXT),
            "title": _trunc(h.book.title, MAX_TITLE),
            "author": _trunc(h.book.author or "", MAX_AUTHOR),
            "category": "books",
            "source_type": "readmoo",
        }
        if h.highlighted_at:
            entry["highlighted_at"] = h.highlighted_at
        if h.note:
            entry["note"] = _trunc(h.note, MAX_NOTE)
        return entry

    def _post(self, batch: List[dict]) -> requests.Response:
        resp = self.session.post(
            f"{READWISE_API}/highlights/",
            json={"highlights": batch},
        )
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 60))
            print(f"\n  [速率限制] 等待 {retry_after} 秒後重試...")
            time.sleep(retry_after)
            resp = self.session.post(
                f"{READWISE_API}/highlights/",
                json={"highlights": batch},
            )
        return resp

    def import_highlights(self, highlights: List["Highlight"]) -> dict:
        """批次送畫線到 Readwise。

        策略：
        1. 預先截斷超長欄位（避開 8191 字元上限）
        2. 整批失敗時，逐筆重送以救回沒問題的畫線
        3. 回傳 failed_indices 讓上層知道哪幾條真正失敗
        """
        self._verify_token()

        payload = [self._build_entry(h) for h in highlights]
        total = len(payload)
        failed_indices: Set[int] = set()
        errors: List[dict] = []

        for i in range(0, total, BATCH_SIZE):
            batch = payload[i: i + BATCH_SIZE]
            resp = self._post(batch)
            time.sleep(RATE_LIMIT_PAUSE)

            if resp.ok:
                continue

            # 整批失敗 → 逐筆重送找出真正壞的那幾條
            print(f"\n  批次 {i}-{i + len(batch)} 整批失敗，逐筆重送補救中...", flush=True)
            for j, item in enumerate(batch):
                single = self._post([item])
                time.sleep(0.15)
                if not single.ok:
                    failed_indices.add(i + j)
                    errors.append({
                        "index": i + j,
                        "status": single.status_code,
                        "body": single.text[:300],
                        "text_preview": item["text"][:80],
                    })

        return {
            "total": total,
            "imported": total - len(failed_indices),
            "failed_indices": failed_indices,
            "errors": errors,
        }

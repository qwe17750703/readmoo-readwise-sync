"""本機同步狀態快取。

紀錄每本書上次同步時看到的畫線數量，下一次同步時若數量沒變就直接跳過。
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

CACHE_PATH = Path(__file__).parent.parent / ".sync_cache.json"


class SyncCache:
    def __init__(self, path: Path = CACHE_PATH):
        self.path = path
        self.data = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"books": {}, "last_full_sync": None}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"books": {}, "last_full_sync": None}

    def get_book(self, reading_id: str) -> Optional[dict]:
        return self.data.get("books", {}).get(reading_id)

    def stage_book(self, reading_id: str, title: str, highlight_count: int) -> None:
        """暫存單一本書的同步狀態，commit() 才會真的寫入磁碟。"""
        self.data.setdefault("books", {})[reading_id] = {
            "title": title,
            "highlight_count": highlight_count,
            "last_synced_at": datetime.now(timezone.utc).isoformat(),
        }

    def commit(self) -> None:
        self.data["last_full_sync"] = datetime.now(timezone.utc).isoformat()
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def clear(self) -> None:
        self.data = {"books": {}, "last_full_sync": None}
        if self.path.exists():
            self.path.unlink()

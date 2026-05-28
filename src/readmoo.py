import time
import requests
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any


@dataclass
class Book:
    id: str
    title: str
    author: str
    reading_id: str


@dataclass
class Highlight:
    text: str
    book: Book
    highlighted_at: Optional[str] = None
    note: Optional[str] = None


class ReadmooClient:
    BASE_URL = "https://api.readmoo.com/store/v3"
    PAGE_SIZE = 10

    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/vnd.api+json",
        })

    def _get(self, path: str, params: dict = None) -> dict:
        url = f"{self.BASE_URL}{path}"
        resp = self.session.get(url, params=params)
        if resp.status_code == 401:
            raise PermissionError("Readmoo Bearer token 無效或已過期，請重新取得。")
        resp.raise_for_status()
        return resp.json()

    def _paginate(self, path: str, extra_params: dict = None) -> List[dict]:
        """Fetch all pages from a paginated endpoint, return combined data list."""
        params = {"page[count]": 0}
        if extra_params:
            params.update(extra_params)
        meta = self._get(path, params)
        total = meta.get("meta", {}).get("total_count", 0)
        if total == 0:
            return []

        results = []
        offset = 0
        while offset <= total:
            params = {"page[count]": self.PAGE_SIZE, "page[offset]": offset}
            if extra_params:
                params.update(extra_params)
            page = self._get(path, params)
            results.append(page)
            offset += self.PAGE_SIZE

        return results

    def get_all_readings(self) -> List[dict]:
        """Return list of {reading_id, book_id, title, author, state}."""
        pages = self._paginate("/me/readings/")
        readings = []
        for page in pages:
            includes_by_id = {
                inc["id"]: inc for inc in page.get("included", [])
                if inc.get("type") == "books"
            }
            for datum in page.get("data", []):
                if datum.get("type") != "readings":
                    continue
                book_id = datum.get("relationships", {}).get("book", {}).get("data", {}).get("id")
                book_inc = includes_by_id.get(book_id, {})
                attrs = book_inc.get("attributes", {})
                readings.append({
                    "reading_id": datum["id"],
                    "book_id": book_id,
                    "title": attrs.get("title", ""),
                    "subtitle": attrs.get("subtitle", ""),
                    "author": attrs.get("author", ""),
                    "state": datum.get("attributes", {}).get("state", ""),
                })
        return readings

    def get_highlight_total_count(self, reading_id: str) -> int:
        """便宜的 API call：只查一本書目前有幾條畫線（不抓內容）。"""
        data = self._get(f"/me/readings/{reading_id}/highlights", {"page[count]": 0})
        return data.get("meta", {}).get("total_count", 0)

    def get_highlights_for_reading(self, reading_id: str) -> List[dict]:
        """Return list of {text, note, highlighted_at} for one reading."""
        pages = self._paginate(f"/me/readings/{reading_id}/highlights")
        highlights = []
        for page in pages:
            ranges_by_id = {
                inc["id"]: inc for inc in page.get("included", [])
                if inc.get("type") == "ranges"
            }
            notes_by_highlight_id = {}
            for inc in page.get("included", []):
                if inc.get("type") == "notes":
                    # notes link back to highlight via relationships
                    hl_id = inc.get("relationships", {}).get("highlight", {}).get("data", {}).get("id")
                    if hl_id:
                        notes_by_highlight_id[hl_id] = inc.get("attributes", {}).get("content", "")

            for datum in page.get("data", []):
                range_id = datum.get("relationships", {}).get("range", {}).get("data", {}).get("id")
                range_inc = ranges_by_id.get(range_id, {})
                text = range_inc.get("attributes", {}).get("content", "").strip()
                if not text:
                    continue
                highlighted_at = datum.get("attributes", {}).get("created_at")
                note = notes_by_highlight_id.get(datum["id"])
                highlights.append({
                    "text": text,
                    "note": note,
                    "highlighted_at": highlighted_at,
                })
        return highlights

    def get_all_highlights(
        self,
        cache=None,
        force: bool = False,
        on_progress=None,
    ) -> Tuple[List[Highlight], Dict[str, dict], Dict[str, int]]:
        """抓所有畫線，並利用快取跳過沒變過的書。

        回傳 (highlights, pending_cache_updates, stats)：
          - highlights：新抓到的畫線（已快取的書不會在這裡）
          - pending_cache_updates：尚未寫入磁碟的快取更新，等 Readwise 成功後再 commit
          - stats：本次同步的統計
        """
        readings = self.get_all_readings()
        all_highlights: List[Highlight] = []
        pending_updates: Dict[str, dict] = {}
        stats = {
            "books_total": len(readings),
            "books_skipped": 0,
            "books_fetched": 0,
            "highlights_new": 0,
        }

        for i, reading in enumerate(readings):
            title = reading["title"]
            if reading.get("subtitle"):
                title += f": {reading['subtitle']}"
            book = Book(
                id=reading["book_id"],
                title=title,
                author=reading["author"],
                reading_id=reading["reading_id"],
            )

            # 便宜的 count 查詢
            current_count = self.get_highlight_total_count(reading["reading_id"])
            cached = cache.get_book(reading["reading_id"]) if cache else None

            if not force and cached and cached.get("highlight_count") == current_count:
                # 數量一致 → 略過
                stats["books_skipped"] += 1
                if on_progress:
                    on_progress(i + 1, len(readings), book.title, skipped=True)
                time.sleep(0.1)
                continue

            # 抓全部畫線
            stats["books_fetched"] += 1
            if on_progress:
                on_progress(i + 1, len(readings), book.title, skipped=False)

            raw_highlights = self.get_highlights_for_reading(reading["reading_id"])
            for h in raw_highlights:
                all_highlights.append(Highlight(
                    text=h["text"],
                    book=book,
                    highlighted_at=h.get("highlighted_at"),
                    note=h.get("note"),
                ))
            stats["highlights_new"] += len(raw_highlights)

            # 紀錄到 pending：Readwise 寫入成功後才會真的 commit
            pending_updates[reading["reading_id"]] = {
                "title": book.title,
                "highlight_count": current_count,
            }
            time.sleep(0.3)

        return all_highlights, pending_updates, stats

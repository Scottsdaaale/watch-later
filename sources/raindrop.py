"""Raindrop.io (experimental): save videos to a collection (default "Watch Later") from the
Raindrop app, its share sheet or browser extension.

New = a bookmark in the collection without the reviewed/failed tag. The review (then as much of
the transcript as fits) goes into the bookmark's note, below any note you wrote, and the
bookmark gets the "reviewed" tag. Failures get "couldnt-process". Remove the tag to retry.

Secret: RAINDROP_TOKEN (a test token from app.raindrop.io/settings/integrations).
config.json:
  "raindrop": { "collection": "Watch Later", "reviewed_tag": "reviewed", "failed_tag": "couldnt-process" }
  Use "collection": "Unsorted" for Raindrop's Unsorted inbox.
"""
from __future__ import annotations

from .base import Item, Source, SourceError, http_json, secret

API = "https://api.raindrop.io/rest/v1"
NOTE_LIMIT = 10000  # Raindrop's note length cap
PER_PAGE = 50


class RaindropSource(Source):
    name = "raindrop"

    def __init__(self, settings=None, dry_run=False):
        super().__init__(settings, dry_run)
        self.collection = str(self.setting("collection", "Watch Later"))
        self.reviewed_tag = self.setting("reviewed_tag", "reviewed")
        self.failed_tag = self.setting("failed_tag", "couldnt-process")
        self._token = None
        self._cid = None

    def _call(self, method, path, body=None):
        if self._token is None:
            self._token = secret("RAINDROP_TOKEN")
        return http_json(method, API + path, self._token, body)

    def collection_id(self) -> int:
        if self._cid is None:
            if self.collection.strip().lower() in ("unsorted", "-1"):
                self._cid = -1
            else:
                found = []
                for path in ("/collections", "/collections/childrens"):
                    found += self._call("GET", path).get("items", [])
                want = self.collection.strip().lower()
                match = [c for c in found if (c.get("title") or "").strip().lower() == want]
                if not match:
                    raise SourceError(f"No Raindrop collection named {self.collection!r}.")
                self._cid = match[0]["_id"]
        return self._cid

    def fetch_new(self) -> list[Item]:
        done = {self.reviewed_tag.lower(), self.failed_tag.lower()}
        items, page = [], 0
        while True:
            data = self._call("GET", f"/raindrops/{self.collection_id()}?perpage={PER_PAGE}&page={page}")
            batch = data.get("items", [])
            for r in batch:
                if done & {t.lower() for t in r.get("tags", [])}:
                    continue
                title = r.get("title") or r.get("link") or ""
                items.append(Item(id=str(r["_id"]), url=r.get("link"), title=title[:100], raw=r))
            if len(batch) < PER_PAGE or page >= 20:
                return items
            page += 1

    def check(self) -> str:
        return f"Raindrop OK: {len(self.fetch_new())} video(s) waiting in {self.collection}"

    def _update(self, item: Item, text: str, tag: str) -> None:
        old = (item.raw.get("note") or "").strip()
        note = f"{old}\n\n---\n{text}" if old else text
        tags = list(item.raw.get("tags", [])) + [tag]
        self._call("PUT", f"/raindrop/{item.id}", {"note": note[:NOTE_LIMIT], "tags": tags})

    def post_review(self, item: Item, review: str, transcript: str) -> None:
        text = review + (f"\n\n---\nTranscript\n\n{transcript}" if transcript else "")
        self._update(item, text, self.reviewed_tag)

    def mark_failed(self, item: Item, reason: str) -> None:
        self._update(item, f"watch-later couldn't process this: {reason}", self.failed_tag)

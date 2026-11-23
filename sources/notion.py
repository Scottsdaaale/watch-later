"""Notion (experimental): a database with a URL property and a Status property.

Save videos as new rows (Notion's share sheet or web clipper). New = a row whose Status isn't the
reviewed/failed value. The review is appended to the row's page (transcript in a toggle) and
Status is set to "Reviewed", or "Couldn't process" with the reason. Clear Status to retry.

Setup: create an internal integration, share the database with it (••• → Connections), and add
the options "Reviewed" and "Couldn't process" to the Status property yourself (the API can't add
options to a Status-type property; a Select-type property gets them automatically).

Secret: NOTION_TOKEN (the integration's "Internal Integration Secret").
config.json:
  "notion": { "database_id": "<id or link>", "url_property": "URL", "status_property": "Status",
              "reviewed_value": "Reviewed", "failed_value": "Couldn't process" }
"""
from __future__ import annotations

import re

from .base import Item, Source, SourceError, find_url, http_json, secret

API = "https://api.notion.com/v1"
VERSION = "2022-06-28"


def _plain(prop: dict) -> str:
    kind = prop.get("type")
    if kind == "url":
        return prop.get("url") or ""
    if kind in ("title", "rich_text"):
        return "".join(x.get("plain_text", "") for x in prop.get(kind, []))
    return ""


def _chunks(text: str, n: int = 1900) -> list[str]:
    return [text[i : i + n] for i in range(0, len(text), n)] or [""]


def _rich(text: str) -> list[dict]:
    return [{"type": "text", "text": {"content": c}} for c in _chunks(text)][:100]


def _para(text: str) -> dict:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rich(text)}}


class NotionSource(Source):
    name = "notion"

    def __init__(self, settings=None, dry_run=False):
        super().__init__(settings, dry_run)
        m = re.search(r"[0-9a-fA-F]{32}", str(self.setting("database_id", "")).replace("-", ""))
        self.db = m.group(0) if m else ""
        self.url_prop = self.setting("url_property", "URL")
        self.status_prop = self.setting("status_property", "Status")
        self.reviewed = self.setting("reviewed_value", "Reviewed")
        self.failed = self.setting("failed_value", "Couldn't process")
        self._token = None
        self._status_type = None

    def _call(self, method, path, body=None):
        if not self.db:
            raise SourceError("Set notion.database_id in config.json (the database's link works too).")
        if self._token is None:
            self._token = secret("NOTION_TOKEN")
        return http_json(method, API + path, self._token, body, {"Notion-Version": VERSION})

    def fetch_new(self) -> list[Item]:
        items, cursor = [], None
        while True:
            body = {"page_size": 100, **({"start_cursor": cursor} if cursor else {})}
            data = self._call("POST", f"/databases/{self.db}/query", body)
            for page in data.get("results", []):
                props = page.get("properties", {})
                status = props.get(self.status_prop)
                if status is None:
                    raise SourceError(f"The database has no property named {self.status_prop!r}.")
                self._status_type = status.get("type")
                value = ((status.get(self._status_type) or {}).get("name") or "") if self._status_type in ("status", "select") else ""
                if value in (self.reviewed, self.failed):
                    continue
                url = find_url(_plain(props.get(self.url_prop, {}))) or find_url(*(_plain(p) for p in props.values()))
                title = next((_plain(p) for p in props.values() if p.get("type") == "title"), "") or url or page["id"]
                items.append(Item(id=page["id"], url=url, title=title[:100], raw=page))
            if not data.get("has_more"):
                return items
            cursor = data.get("next_cursor")

    def check(self) -> str:
        return f"Notion OK: {len(self.fetch_new())} video(s) waiting"

    def _set_status(self, item: Item, value: str) -> None:
        kind = self._status_type if self._status_type in ("status", "select") else "select"
        self._call("PATCH", f"/pages/{item.id}", {"properties": {self.status_prop: {kind: {"name": value}}}})

    def post_review(self, item: Item, review: str, transcript: str) -> None:
        blocks = [{"object": "block", "type": "heading_2", "heading_2": {"rich_text": _rich("watch-later review")}}]
        blocks += [_para(p.strip()) for p in review.split("\n\n") if p.strip()][:80]
        if transcript:
            parts = [_para(c) for c in _chunks(transcript, 1900 * 40)][:10]
            blocks.append({"object": "block", "type": "toggle", "toggle": {"rich_text": _rich("Transcript"), "children": parts}})
        self._call("PATCH", f"/blocks/{item.id}/children", {"children": blocks[:100]})
        self._set_status(item, self.reviewed)

    def mark_failed(self, item: Item, reason: str) -> None:
        self._call("PATCH", f"/blocks/{item.id}/children", {"children": [_para(f"watch-later couldn't process this: {reason}")]})
        self._set_status(item, self.failed)

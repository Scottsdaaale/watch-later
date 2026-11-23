"""The source interface: where videos come from, and where their reviews go back."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

URL_RE = re.compile(r"https?://[^\s)\]>\"'`]+")

# Values from the .env file. Kept here, not in os.environ, so they're never inherited by the
# `claude -p` subprocess that reviews (untrusted) videos. Filled by watch_later.load_env_file().
ENV_VALUES: dict[str, str] = {}

# Source secrets, also removed from the environment Claude runs in if they're set there.
SECRET_NAMES = ("TODOIST_API_TOKEN", "TODOIST_API_KEY", "RAINDROP_TOKEN", "NOTION_TOKEN")


@dataclass
class Item:
    """One saved video."""

    id: str
    url: str | None
    title: str  # shown in logs
    raw: Any = None  # whatever the source needs later (the task, the line, the page...)


class SourceError(RuntimeError):
    """A readable setup problem: missing token, project not found, and so on."""


class Source:
    """A place where you save videos to review, and where the reviews go back.

    To add one (Google Sheets, Telegram, Discord, email...): create sources/<name>.py with a
    subclass that implements the four methods below, and add it to SOURCES in sources/__init__.py.
    `settings` is the config.json block named after the source. Secrets come from environment
    variables; watch_later.py loads .env into the environment before creating the source.
    `dry_run` is True for --dry-run and --check: don't change anything in the source then.
    """

    name = "base"

    def __init__(self, settings: dict | None = None, dry_run: bool = False):
        self.settings = settings or {}
        self.dry_run = dry_run

    def setting(self, key: str, default: Any) -> Any:
        return self.settings.get(key, default)

    def check(self) -> str:
        """Verify access without changing anything. Return a one-line status; raise SourceError."""
        raise NotImplementedError

    def fetch_new(self) -> list[Item]:
        """Saved videos that haven't been reviewed or failed yet."""
        raise NotImplementedError

    def post_review(self, item: Item, review: str, transcript: str) -> None:
        """Attach the review (and transcript) to the item and mark it reviewed."""
        raise NotImplementedError

    def mark_failed(self, item: Item, reason: str) -> None:
        """Mark the item as couldn't-process with the reason, so it isn't retried every night."""
        raise NotImplementedError


def find_url(*texts: str | None) -> str | None:
    for text in texts:
        m = URL_RE.search(text or "")
        if m:
            return m.group(0).rstrip(".,;:!?")
    return None


def secret(*names: str) -> str:
    """The first non-empty value among `names`, from the environment or .env. Never log it."""
    for name in names:
        value = (os.environ.get(name) or ENV_VALUES.get(name) or "").strip()
        if value:
            return value
    raise SourceError(f"No {names[0]} found. Add it to .env (see .env.example) or set it in the environment.")


def http_json(method: str, url: str, token: str, body: Any = None, headers: dict | None = None, timeout: int = 30) -> Any:
    """Small JSON-over-HTTPS helper (stdlib only) with Bearer auth."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise SourceError(f"{method} {url} failed: HTTP {e.code} {detail}") from None
    except urllib.error.URLError as e:
        raise SourceError(f"{method} {url} failed: {e.reason}") from None
    return json.loads(raw) if raw else {}

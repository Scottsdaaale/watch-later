"""A Markdown/text file of links ("inbox").

Made for an iPhone Shortcut in the share sheet (Share → "Watch Later" → Append to Text File in
iCloud Drive or Dropbox; see SETUP.md), but anything that adds a line to the file works, including
pasting on the PC. Each line with a link is one video. After review the line is ticked off with a
link to a Markdown review file; failures are marked "- [!]" with the reason.

config.json:
  "inbox": { "path": "inbox.md", "reviews_dir": "" }   # reviews_dir defaults to <inbox folder>/reviews
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

from .base import Item, Source, SourceError, find_url

ROOT = Path(__file__).resolve().parent.parent
DONE = re.compile(r"^\s*[-*]\s*\[(x|X|!)\]")
MARKER = re.compile(r"^\s*[-*]\s*(\[ \]\s*)?")

TEMPLATE = """# Watch Later

Paste one link per line. Anything else on the line is kept as your note.
Reviewed links get ticked off with a link to their review. To review one again,
change its "- [x]" or "- [!]" back to "- [ ]".

"""


def _resolve(value: str) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else ROOT / p


class InboxSource(Source):
    name = "inbox"

    @property
    def path(self) -> Path:
        return _resolve(self.setting("path", "inbox.md"))

    @property
    def reviews_dir(self) -> Path:
        d = self.setting("reviews_dir", "")
        return _resolve(d) if d else self.path.parent / "reviews"

    def create(self) -> None:
        """Create the inbox file with instructions (used by setup)."""
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(TEMPLATE, encoding="utf-8")

    def _lines(self) -> list[str]:
        if not self.path.exists():
            raise SourceError(f"{self.path} doesn't exist yet. Run: python watch_later.py --init-inbox")
        return self.path.read_text(encoding="utf-8").splitlines()

    def check(self) -> str:
        return f"Inbox OK: {len(self.fetch_new())} link(s) waiting in {self.path}"

    def fetch_new(self) -> list[Item]:
        items = []
        for i, line in enumerate(self._lines()):
            if DONE.match(line):
                continue
            url = find_url(line)
            if url:
                items.append(Item(id=str(i), url=url, title=line.strip()[:100], raw=line))
        return items

    def _replace_line(self, item: Item, new_line: str) -> None:
        lines = self._lines()
        for i, line in enumerate(lines):
            if line == item.raw:
                lines[i] = new_line
                break
        else:  # the line was edited meanwhile: keep the result at the end rather than lose it
            lines.append(new_line)
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _text(line: str) -> str:
        return MARKER.sub("", line, count=1).strip()

    def post_review(self, item: Item, review: str, transcript: str) -> None:
        self.reviews_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", (item.url or "video").split("://", 1)[-1]).strip("-")[:60]
        out = self.reviews_dir / f"{datetime.now():%Y-%m-%d}-{slug}.md"
        body = f"# Review\n\n<{item.url}>\n\n{review}\n"
        if transcript:
            body += f"\n<details><summary>Transcript</summary>\n\n{transcript}\n\n</details>\n"
        out.write_text(body, encoding="utf-8")
        try:
            link = os.path.relpath(out, self.path.parent).replace("\\", "/")
        except ValueError:  # different drive on Windows
            link = out.as_uri()
        self._replace_line(item, f"- [x] {self._text(item.raw)} → [review](<{link}>)")

    def mark_failed(self, item: Item, reason: str) -> None:
        reason = " ".join(reason.split())[:200]
        self._replace_line(item, f"- [!] {self._text(item.raw)} — couldn't process: {reason}")

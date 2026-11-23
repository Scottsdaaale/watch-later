"""Save sources: where videos come from and where their reviews go back.

Pick one with "source" in config.json. To add your own, see Source in sources/base.py and
"Adding a source" in SETUP.md.
"""
import importlib

from .base import Item, Source, SourceError, find_url  # noqa: F401

# name -> (module, class). Modules are imported only when used, so a source's
# dependencies are only needed if you pick it.
SOURCES = {
    "inbox": ("inbox", "InboxSource"),
    "todoist": ("todoist", "TodoistSource"),
    "raindrop": ("raindrop", "RaindropSource"),
    "notion": ("notion", "NotionSource"),
}


def load_source(cfg: dict, dry_run: bool = False) -> Source:
    name = cfg.get("source", "inbox")
    if name not in SOURCES:
        raise SourceError(f"Unknown source {name!r} in config.json. Known: {', '.join(SOURCES)}.")
    module, cls = SOURCES[name]
    return getattr(importlib.import_module(f".{module}", __package__), cls)(cfg.get(name, {}), dry_run)

"""Todoist: share videos into a project (default "Watch Later").

New = an open task in the project that isn't in a section. The review and transcript are posted
as comments and the task moves to "Reviewed"; failures move to "Couldn't process" with the
reason as a comment. To review a task again, drag it out of its section.

Secret: TODOIST_API_TOKEN (TODOIST_API_KEY also works).
config.json:
  "todoist": { "project_name": "Watch Later", "reviewed_section": "Reviewed", "failed_section": "Couldn't process" }
"""
from __future__ import annotations

from .base import Item, Source, SourceError, find_url, secret


class TodoistSource(Source):
    name = "todoist"

    def __init__(self, settings=None, dry_run=False):
        super().__init__(settings, dry_run)
        self.project_name = self.setting("project_name", "Watch Later")
        self.reviewed = self.setting("reviewed_section", "Reviewed")
        self.failed = self.setting("failed_section", "Couldn't process")
        self._api = None
        self._project = None
        self._sections = None

    @property
    def api(self):
        if self._api is None:
            try:
                from todoist_api_python.api import TodoistAPI
            except ImportError:
                raise SourceError("todoist-api-python isn't installed (pip install todoist-api-python).") from None
            self._api = TodoistAPI(secret("TODOIST_API_TOKEN", "TODOIST_API_KEY"))
        return self._api

    def project(self):
        if self._project is None:
            self._project = next(
                (p for page in self.api.get_projects() for p in page if p.name == self.project_name), None
            )
            if self._project is None:
                raise SourceError(f"No Todoist project named {self.project_name!r}.")
        return self._project

    def section_id(self, name: str) -> str:
        if self._sections is None:
            self._sections = {
                s.name: s.id for page in self.api.get_sections(project_id=self.project().id) for s in page
            }
        if name not in self._sections:
            self._sections[name] = self.api.add_section(name, project_id=self.project().id).id
        return self._sections[name]

    def check(self) -> str:
        return f"Todoist OK: {len(self.fetch_new())} video(s) waiting in {self.project_name}"

    def fetch_new(self) -> list[Item]:
        tasks = [t for page in self.api.get_tasks(project_id=self.project().id) for t in page if not t.section_id]
        return [
            Item(id=t.id, url=find_url(t.content, t.description), title=t.content[:100], raw=t) for t in tasks
        ]

    def post_review(self, item: Item, review: str, transcript: str) -> None:
        self.api.add_comment(review[:15000], task_id=item.id)
        if transcript:
            self.api.add_comment(("**Transcript**\n\n" + transcript)[:15000], task_id=item.id)
        self.api.move_task(item.id, section_id=self.section_id(self.reviewed))

    def mark_failed(self, item: Item, reason: str) -> None:
        self.api.add_comment(f"watch-later couldn't process this: {reason}", task_id=item.id)
        self.api.move_task(item.id, section_id=self.section_id(self.failed))

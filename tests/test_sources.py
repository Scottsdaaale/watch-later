"""Offline tests: every source and the nightly loop, with fakes. No tokens, network or GPU needed.

Run:  python -m unittest discover -s tests -t .
"""
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import watch_later
from sources import Item, SourceError, base, find_url, load_source
from sources import notion as notion_mod
from sources import raindrop as raindrop_mod
from sources.inbox import InboxSource
from sources.notion import NotionSource
from sources.raindrop import RaindropSource
from sources.todoist import TodoistSource


class FakeHTTP:
    """Stands in for sources.base.http_json. Routes match on (method, URL fragment), in order."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, method, url, token, body=None, headers=None, timeout=30):
        self.calls.append(SimpleNamespace(method=method, url=url, token=token, body=body, headers=headers or {}))
        for (m, fragment), response in self.routes:
            if m == method and fragment in url:
                return response
        raise AssertionError(f"unexpected call: {method} {url}")


class HelpersTest(unittest.TestCase):
    def test_find_url(self):
        self.assertEqual(find_url("watch https://youtu.be/abc."), "https://youtu.be/abc")
        self.assertEqual(find_url("", None, "see (https://x.example/a?b=1)"), "https://x.example/a?b=1")
        self.assertIsNone(find_url("no link"))

    def test_unknown_source(self):
        with self.assertRaises(SourceError):
            load_source({"source": "myspace"})

    def test_env_file_stays_out_of_the_environment(self):
        with tempfile.TemporaryDirectory() as d:
            env = Path(d) / ".env"
            env.write_text('# comment\nWL_TEST_A="one"\nexport WL_TEST_B=two\nWL_TEST_C=\n', encoding="utf-8")
            with mock.patch.dict(os.environ, {"WL_TEST_B": "already-set"}), mock.patch.dict(base.ENV_VALUES, clear=True):
                watch_later.load_env_file({"env_file": str(env)})
                self.assertNotIn("WL_TEST_A", os.environ)  # never inherited by the claude subprocess
                self.assertEqual(base.secret("WL_TEST_A"), "one")
                self.assertEqual(base.secret("WL_TEST_B"), "already-set")  # the environment wins
                self.assertNotIn("WL_TEST_C", base.ENV_VALUES)

    def test_review_tools_are_read_only_and_file_free(self):
        tools = watch_later.allowed_tools(watch_later.DEFAULTS)
        for t in tools:
            self.assertFalse(t.startswith(("Read", "Glob", "Grep", "Edit", "Write")), t)
            self.assertNotRegex(t, r"(?i)\b(add|delete|set|setactive|install|import)\b", t)
        for t in ("Read", "Glob", "Grep", "Edit", "Write", "PowerShell"):
            self.assertIn(t, watch_later.DISALLOWED_TOOLS)
        self.assertEqual(watch_later.allowed_tools({"inspect_pc": False}), ["WebSearch", "WebFetch"])


class InboxTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.inbox = Path(self.tmp.name) / "inbox.md"
        self.src = InboxSource({"path": str(self.inbox)})
        self.src.create()
        with open(self.inbox, "a", encoding="utf-8") as f:
            f.write(
                "https://www.instagram.com/reel/AAA/\n"
                "- https://youtu.be/BBB check the router one\n"
                "- [x] https://done.example/x → [review](<reviews/x.md>)\n"
                "no link on this line\n"
            )

    def tearDown(self):
        self.tmp.cleanup()

    def test_fetch_new_skips_done_and_plain_lines(self):
        self.assertEqual(
            [i.url for i in self.src.fetch_new()], ["https://www.instagram.com/reel/AAA/", "https://youtu.be/BBB"]
        )

    def test_review_and_failure_are_recorded(self):
        a, b = self.src.fetch_new()
        self.src.post_review(a, "**Verdict:** ✅ Worth doing", "the transcript")
        self.src.mark_failed(b, "Download failed: login required\n(more)")
        text = self.inbox.read_text(encoding="utf-8")
        self.assertIn("- [x] https://www.instagram.com/reel/AAA/ → [review](<reviews/", text)
        self.assertIn("- [!] https://youtu.be/BBB check the router one — couldn't process: Download failed: login required (more)", text)
        self.assertEqual(self.src.fetch_new(), [])
        reviews = list((self.inbox.parent / "reviews").glob("*.md"))
        self.assertEqual(len(reviews), 1)
        body = reviews[0].read_text(encoding="utf-8")
        self.assertIn("**Verdict:** ✅ Worth doing", body)
        self.assertIn("the transcript", body)

    def test_missing_inbox_is_a_readable_error(self):
        with self.assertRaises(SourceError):
            InboxSource({"path": str(Path(self.tmp.name) / "nope.md")}).fetch_new()


class FakeTodoist:
    def __init__(self):
        self.comments, self.moves, self.added = [], [], []

    def get_projects(self):
        yield [SimpleNamespace(id="P", name="Other"), SimpleNamespace(id="P1", name="Watch Later")]

    def get_sections(self, project_id):
        yield [SimpleNamespace(id="S-rev", name="Reviewed")]

    def get_tasks(self, project_id):
        yield [
            SimpleNamespace(id="T1", content="Power plan tip", description="https://www.instagram.com/reel/AAA/", section_id=None),
            SimpleNamespace(id="T2", content="https://old.example", description="", section_id="S-rev"),
        ]

    def add_section(self, name, project_id):
        self.added.append(name)
        return SimpleNamespace(id="S-new")

    def add_comment(self, content, task_id):
        self.comments.append((task_id, content))

    def move_task(self, task_id, section_id):
        self.moves.append((task_id, section_id))


class TodoistTest(unittest.TestCase):
    def test_flow(self):
        src = TodoistSource({})
        src._api = FakeTodoist()
        items = src.fetch_new()
        self.assertEqual([(i.id, i.url) for i in items], [("T1", "https://www.instagram.com/reel/AAA/")])
        src.post_review(items[0], "REVIEW", "TRANSCRIPT")
        self.assertEqual(src.api.comments[0], ("T1", "REVIEW"))
        self.assertTrue(src.api.comments[1][1].startswith("**Transcript**"))
        self.assertEqual(src.api.moves[-1], ("T1", "S-rev"))
        src.mark_failed(items[0], "nope")
        self.assertEqual(src.api.added, ["Couldn't process"])
        self.assertEqual(src.api.moves[-1], ("T1", "S-new"))


class RaindropTest(unittest.TestCase):
    def test_flow(self):
        http = FakeHTTP([
            (("GET", "/collections/childrens"), {"items": [{"_id": 7, "title": "Nested"}]}),
            (("GET", "/collections"), {"items": [{"_id": 42, "title": "Watch Later"}]}),
            (("GET", "/raindrops/42"), {"items": [
                {"_id": 1, "link": "https://www.instagram.com/reel/AAA/", "title": "A", "tags": ["pc"], "note": "my note"},
                {"_id": 2, "link": "https://x.example", "title": "B", "tags": ["Reviewed"]},
            ]}),
            (("PUT", "/raindrop/1"), {"result": True}),
        ])
        with mock.patch.dict(os.environ, {"RAINDROP_TOKEN": "fake"}), mock.patch.object(raindrop_mod, "http_json", http):
            src = RaindropSource({})
            items = src.fetch_new()
            self.assertEqual([i.id for i in items], ["1"])
            src.post_review(items[0], "REVIEW", "TRANSCRIPT")
        put = http.calls[-1]
        self.assertEqual(put.method, "PUT")
        self.assertTrue(put.body["note"].startswith("my note\n\n---\nREVIEW"))
        self.assertIn("TRANSCRIPT", put.body["note"])
        self.assertEqual(put.body["tags"], ["pc", "reviewed"])


class NotionTest(unittest.TestCase):
    def page(self, pid, status):
        return {
            "id": pid,
            "properties": {
                "Name": {"type": "title", "title": [{"plain_text": f"Reel {pid}"}]},
                "URL": {"type": "url", "url": f"https://www.instagram.com/reel/{pid}/"},
                "Status": {"type": "status", "status": {"name": status} if status else None},
            },
        }

    def test_flow(self):
        http = FakeHTTP([
            (("POST", "/databases/0123456789abcdef0123456789abcdef/query"),
             {"results": [self.page("p1", None), self.page("p2", "Reviewed"), self.page("p3", "Not started")], "has_more": False}),
            (("PATCH", "/blocks/"), {}),
            (("PATCH", "/pages/"), {}),
        ])
        link = "https://www.notion.so/me/Watch-Later-0123456789abcdef0123456789abcdef?v=fedcba9876543210fedcba9876543210"
        with mock.patch.dict(os.environ, {"NOTION_TOKEN": "fake"}), mock.patch.object(notion_mod, "http_json", http):
            src = NotionSource({"database_id": link})
            items = src.fetch_new()
            self.assertEqual([i.id for i in items], ["p1", "p3"])
            self.assertEqual(items[0].url, "https://www.instagram.com/reel/p1/")
            src.post_review(items[0], "**Verdict:** ✅\n\nSecond paragraph", "T" * 5000)
            src.mark_failed(items[1], "no audio")
        blocks = http.calls[1].body["children"]
        self.assertEqual(blocks[0]["type"], "heading_2")
        self.assertEqual(blocks[-1]["type"], "toggle")
        self.assertTrue(all(len(t["text"]["content"]) <= 2000 for b in blocks for t in b.get(b["type"], {}).get("rich_text", [])))
        self.assertEqual(http.calls[2].body, {"properties": {"Status": {"status": {"name": "Reviewed"}}}})
        self.assertEqual(http.calls[-1].body, {"properties": {"Status": {"status": {"name": "Couldn't process"}}}})
        self.assertEqual(http.calls[0].headers.get("Notion-Version"), notion_mod.VERSION)


class FakeSource:
    name = "fake"

    def __init__(self, items):
        self.items, self.posted, self.failed = items, [], []

    def fetch_new(self):
        return self.items

    def post_review(self, item, review, transcript):
        self.posted.append((item.id, review, transcript))

    def mark_failed(self, item, reason):
        self.failed.append((item.id, reason))


class RunTest(unittest.TestCase):
    items = [
        Item("1", "https://ok.example/a", "good one"),
        Item("2", None, "no link"),
        Item("3", "https://bad.example/b", "broken one"),
    ]

    @staticmethod
    def fake_review(url, cfg):
        if "bad" in url:
            raise RuntimeError("Download failed: nope")
        return "REVIEW", "TRANSCRIPT"

    def run_with(self, dry_run):
        src = FakeSource(self.items)
        with mock.patch.object(watch_later, "review_one", self.fake_review), \
                mock.patch.object(watch_later, "log", lambda msg: None), \
                contextlib.redirect_stdout(io.StringIO()):
            watch_later.run(dict(watch_later.DEFAULTS), dry_run=dry_run, source=src)
        return src

    def test_reviews_and_failures(self):
        src = self.run_with(dry_run=False)
        self.assertEqual(src.posted, [("1", "REVIEW", "TRANSCRIPT")])
        self.assertEqual([f[0] for f in src.failed], ["2", "3"])
        self.assertIn("No link", src.failed[0][1])
        self.assertIn("Download failed", src.failed[1][1])

    def test_dry_run_changes_nothing(self):
        src = self.run_with(dry_run=True)
        self.assertEqual((src.posted, src.failed), ([], []))


if __name__ == "__main__":
    unittest.main()

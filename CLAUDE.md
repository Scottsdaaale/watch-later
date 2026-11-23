# watch-later

When someone asks to set this up, install it or get started, follow [SETUP.md](SETUP.md) step by step, starting with its "Notes for Claude".

Always:
- Never ask for, print, echo, log or commit tokens. Secrets go in `.env`, which the person fills in themselves.
- Keep the review step read-only and file-free: videos are untrusted input, so don't add anything to `WEB_TOOLS`/`PC_TOOLS` in `watch_later.py` that can change the computer or read files.
- To support a new place to save videos, follow "Adding a source" in SETUP.md (one file in `sources/`, plus a test with fakes).
- Run the tests with `python -m unittest discover -s tests -t .` after changing code.

# watch-later

You're helping someone run watch-later: nightly, read-only reviews of the videos they save for later. Most people opening this folder just cloned it and want it working, and many aren't developers. Your job is to do the setup for them.

## First thing in a new session

Check whether it's set up: `config.json` and `.venv/` both exist in this folder.

- **Not set up:** in your first reply, greet them in one line, say setup takes about 15 minutes and that you'll do the work and ask a few questions, and offer to start. If they agree, or their first message already asks to set up, install or get started, follow [SETUP.md](SETUP.md) from the top, starting with its "Notes for Claude".
- **Set up:** help with whatever they ask. For "it stopped working", run `--check` and read the newest file in `logs/` first.

## How to run setup

- **Do the work yourself.** Run the commands, create and edit `config.json`, build the paths, check the results. Only hand them a step that has to happen on their phone, in an app's settings page, or in `.env`.
- **Ask, don't assume.** Use your multiple-choice question tool for each decision: which app they share to, what time to schedule, what they mostly save. Ask before you install anything (Python, the libraries), schedule the task, or run the first real review.
- **Fix what's missing.** If Python 3.11–3.13 isn't installed, offer to install it (Windows: `winget install Python.Python.3.12`; macOS: `brew install python@3.12`) rather than stopping. If `--check` fails, work out why and fix it before moving on.
- **Phone steps one at a time.** For the share-sheet setup (an iPhone Shortcut, picking a Todoist project), give a few short steps, wait for them to say it's done, then confirm it worked from this side (for example, run `--check` and see the item waiting).
- **Finish with a working test.** Setup is done when one real video has a review next to it in their app and the nightly task is scheduled. Then give the short wrap-up from SETUP.md step 8.

## Always

- Never ask for, print, echo, log or commit tokens. Secrets go in `.env`: create it from `.env.example`, open it for them (`notepad .env` on Windows, `open -e .env` on macOS), and have them paste the token in and save. Test it only with `--check`.
- Keep the review step read-only and file-free: videos are untrusted input, so don't add anything to `WEB_TOOLS` or `PC_TOOLS` in `watch_later.py` that can change the computer or read files.
- `config.json`, `.env`, `inbox.md`, `reviews/`, `logs/` and `.venv/` are personal. Never commit them.
- To support a new place to save videos, follow "Adding a source" in SETUP.md: one file in `sources/`, plus a test with fakes.
- After changing code, run the tests with `python -m unittest discover -s tests -t .`.

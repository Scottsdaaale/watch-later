# Setting up watch-later

> **Easiest way:** open this folder in [Claude Code](https://docs.claude.com/en/docs/claude-code) (`claude`) and type **`/setup`** (or say "set this up"). Claude follows this file step by step, does the installing for you and asks a few questions along the way.
> Prefer doing it yourself? Every step below has the commands.

Total time: about 15 minutes, most of it downloads.

## Notes for Claude

- Go one step at a time. Say what you're about to do and why, in plain words.
- Ask before you install anything, schedule the nightly task, or run the first real (non-dry) review.
- **Secrets:** never ask the person to paste a token into the chat, and never print, echo, log or commit one. Create `.env` from `.env.example` and ask them to open it and paste the token themselves. Test a token only by running `--check`.
- Never widen `WEB_TOOLS` or `PC_TOOLS` in `watch_later.py` with anything that can change the computer or read files (no `reg add`, `Set-*`, `powercfg /setactive`, installers, `Read`, file writes). Videos are untrusted input, so the review step must stay read-only and file-free (see "Security" in README.md).
- `config.json`, `.env`, `inbox.md`, `reviews/`, `logs/` and `.venv/` are personal and gitignored. Don't commit them.
- In the commands below, `<python>` means `.\.venv\Scripts\python.exe` on Windows and `.venv/bin/python` on macOS/Linux.

## 1. Check the basics

| Need | Check | If missing |
|---|---|---|
| Python **3.11–3.13** (3.14 is too new for the Whisper libraries; 3.10 still works, but yt-dlp is dropping it) | Windows: `py -0p` · macOS/Linux: `python3.12 --version` (or 3.13/3.11) | Install 3.12 from python.org. On Windows, tick **"Add python.exe to PATH"**. |
| Claude Code, signed in | `claude --version` | Install it, then run `claude` once and sign in. |
| NVIDIA GPU (optional) | `nvidia-smi` | Fine without one. Transcription uses the CPU and a smaller model, which is plenty for short videos. |

Windows is the main target: the reviews check the PC's settings with Windows commands. On macOS and Linux everything else works; the reviews just won't inspect the computer.

## 2. Ask which app they share videos to

The whole point is zero friction: on the video, tap **Share**, pick an app, done. So ask (use your multiple-choice question tool if you have one): **"When you hit Share on a reel, TikTok or Short you want to look at later, which app do you send it to?"**

| Their answer | Share straight from the video? | `source` | Status |
|---|---|---|---|
| Todoist | ✅ iPhone and Android | `todoist` | Tested, in daily use |
| Raindrop.io | ✅ iPhone and Android | `raindrop` | Experimental |
| Notion | ✅ iPhone and Android (pick the database in the share sheet) | `notion` | Experimental |
| A note or file (Apple Notes, Obsidian...) | ✅ iPhone, through a Shortcut that shows up in the share sheet · ❌ Android without extra apps | `inbox` | Tested |
| Nothing yet | | | Recommend **Todoist** or **Raindrop.io**: both are free and both appear in the share sheet on iPhone and Android. |
| Another app that's in their share sheet (Telegram, Discord, Slack, Microsoft To Do, email...) | ✅ | new adapter | See [Adding a source](#adding-a-source) |

If they only tap Instagram's own bookmark (its "Saved" folder), explain that Instagram doesn't let tools read it, so they'll use **Share → their app** instead. It's the same number of taps.

Then copy `config.example.json` to `config.json` and set `"source"`. The review always goes back to the same place they shared the video to.

## 3. Connect the source

Copy `.env.example` to `.env` if the source needs a token.

### inbox (a Markdown file, shared to from an iPhone Shortcut)
The file has to live somewhere both the phone and this PC can reach: **iCloud Drive** (the PC needs the iCloud for Windows app) or **Dropbox** (the PC needs the Dropbox app).

1. **On the PC:** pick the file's location inside that synced folder, for example `iCloud Drive\watch-later\inbox.md`. Set `"inbox": { "path": "<full path>" }` in `config.json` and create the file with `<python> watch_later.py --init-inbox` (after step 4, or with any Python for now).
2. **On the iPhone:** build a Shortcut called **Watch Later** in the Shortcuts app:
   - Tap the **ⓘ** (Details) and turn on **Show in Share Sheet**. Under "Receives", keep only **URLs**.
   - Add the action **Append to Text File**. Set it to append **Shortcut Input**, choose the same file (iCloud Drive → `watch-later/inbox.md`, or the Dropbox path), and turn on **Make New Line**.
   - Optional: add **Show Notification** "Saved for later" so they know it worked.
3. **Try it:** on a reel, tap **Share → Watch Later** (it may be under "More" the first time; they can drag it to the front). The link appears as a new line in `inbox.md` once the file syncs to the PC.
4. Reviews are written to a `reviews` folder next to the inbox file (so they can read them on the phone too), and each line gets ticked off with a link to its review.

On Android there's no built-in way to append a shared link to a file, so steer Android users to Todoist or Raindrop instead.

### todoist
1. Create a project called **Watch Later** (or pick an existing one and set `"todoist": { "project_name": "..." }`).
2. Token: Todoist → **Settings → Integrations → Developer → API token**. Ask them to paste it into `.env` as `TODOIST_API_TOKEN=...` and save.
3. On the phone: share a video → Todoist → pick the project. The link can be in the task name or description.
4. Reviews arrive as comments; the task moves to a **Reviewed** section (created automatically). Failures go to **Couldn't process**.

### raindrop (experimental)
1. Create a collection called **Watch Later** (or set `"raindrop": { "collection": "..." }`; `"Unsorted"` works too).
2. Token: [app.raindrop.io/settings/integrations](https://app.raindrop.io/settings/integrations) → **Create new app** → open it → **Create test token**. Ask them to paste it into `.env` as `RAINDROP_TOKEN=...`.
3. On the phone: share → Raindrop → the collection.
4. Reviews go into the bookmark's note (below any note they wrote), and the bookmark gets the tag `reviewed` (or `couldnt-process`).

### notion (experimental)
1. A database (table) with a **URL** property (type URL) and a **Status** property (type Status or Select). Add the options **Reviewed** and **Couldn't process** to Status. Notion's API can't add options to a Status-type property, so they have to exist. Different names? Set them in `config.json`.
2. Token: [notion.so/profile/integrations](https://www.notion.so/profile/integrations) → **New integration** (internal) → copy the **Internal Integration Secret**. Ask them to paste it into `.env` as `NOTION_TOKEN=...`.
3. Give the integration access: open the database → **•••** → **Connections** → add the integration.
4. Put the database's link in `config.json` as `"notion": { "database_id": "<link>" }`.
5. On the phone: share → Notion → the database. The review is added to the row's page and Status is set.

## 4. Install

Ask first: this downloads about 1–2 GB with GPU libraries, 0.5 GB without.

- **Windows:** `powershell -ExecutionPolicy Bypass -File .\install.ps1 -NoSchedule`
- **macOS/Linux:** `bash install.sh`

Both create `.venv`, install the libraries and finish with `--check`.

## 5. Check and test

1. `<python> watch_later.py --check` should print three good lines: libraries OK (with the GPU count), `claude: found`, and `<Source> OK: N waiting`. Fix anything else before going on.
2. **One test review that changes nothing:** ask them for a link (or use one they've saved), then run `<python> watch_later.py --url "<link>"`. It takes 1–3 minutes; the first run also downloads the Whisper model. Show them the review.
3. With their OK, **one real run:** `<python> watch_later.py`. Then have them look in their app (or the inbox file) to see the review next to the video.

Common problems:
- **Instagram asks yt-dlp to log in / rate-limits:** update yt-dlp first (`<python> -m pip install -U yt-dlp`). If it still fails, set `"cookies_from_browser": "firefox"` in `config.json` (or `"chrome"`, which must be closed while it runs).
- **CUDA errors (cublas/cudnn DLL not found):** the CPU fallback kicks in automatically; that's fine for short videos.
- **`UnicodeEncodeError`:** set `PYTHONUTF8=1` for the scheduled run.

## 6. Schedule it

Ask what time works (default 02:30; the computer has to be on and logged in, or it catches up later on Windows).

- **Windows:** `powershell -ExecutionPolicy Bypass -File .\install.ps1 -Time "02:30"` registers **"Watch Later review"** in Task Scheduler. Confirm with `Get-ScheduledTask "Watch Later review" | Get-ScheduledTaskInfo`.
- **Linux:** add the cron line `install.sh` printed (`crontab -e`).
- **macOS:** cron skips runs while the Mac sleeps. A LaunchAgent catches up: create `~/Library/LaunchAgents/com.watch-later.plist` with `ProgramArguments` = `[<full path to .venv/bin/python>, <full path to watch_later.py>]`, `WorkingDirectory` = this folder, and `StartCalendarInterval` = `{Hour: 2, Minute: 30}`; then `launchctl load` it. Ask before creating it.

## 7. Make the reviews theirs (optional)

Ask what they mostly save (PC and gaming tips, coding tools, productivity apps, cooking, fitness...) and what this computer is. Rewrite the short **About the owner** section at the top of `prompt.md` to match. Leave the "What you may do" rules alone.

## 8. Wrap up

Tell them, in a few lines:
- how to save a video (the share-sheet steps for their source),
- when reviews appear and where,
- how to review one again (Todoist: drag it out of its section · inbox: change `- [x]` back to `- [ ]` · Raindrop: remove the tag · Notion: clear Status),
- where the logs are (`logs/`), and that `<python> -m pip install -U yt-dlp` fixes most download failures.

## Adding a source

When their app isn't listed, write an adapter. Each source is one small file:

1. Create `sources/<name>.py` with a class that subclasses `Source` (see `sources/base.py`) and implements:
   - `check()`: verify access, change nothing, return a one-line status;
   - `fetch_new()`: return `Item`s for saved videos not yet reviewed or failed;
   - `post_review(item, review, transcript)`: put the review next to the video and mark it done;
   - `mark_failed(item, reason)`: mark it so it isn't retried every night.
   `sources/raindrop.py` is a good template for any app with a REST API (`http_json` and `secret` in `base.py` do the HTTP and token parts).
2. Add it to `SOURCES` in `sources/__init__.py`, its settings to `config.example.json`, and any token name to `.env.example`.
3. Test with fakes first (see `tests/test_sources.py`), then `--check`, then `--dry-run`, then one real run with their OK.

Notes for common requests:
- **Google Sheets:** a sheet with a URL column and a Status column, using a service account (`gspread`); share the sheet with the service account's email.
- **Telegram:** a bot they message links to. The Bot API keeps unread updates for only 24 hours, so either run more often than nightly or have the bot post into a private channel and read that.
- **Discord:** a bot reading a private channel; reply in a thread with the review.
- **Email:** an IMAP folder (for example a "Watch Later" label in Gmail with an app password); reply or move the message when done.

# watch-later

**You save every "you NEED to try this" reel… and never actually try any of them. This follows up for you.**

Every night, watch-later picks up the videos you saved for later, transcribes them on your own PC, and has Claude Code research each tip and check whether it even applies to your computer, **read-only**. By morning, every saved video has a verdict next to it:

> **Verdict:** ✅ Worth doing · 🟡 Maybe / depends · ⏭️ Skip · ☑️ Already set on this PC
> plus what the video claims, whether it's true (with sources), what your PC has now, and the steps (and how to undo them) if it's worth doing.

## How it works

```
your save spot ──► yt-dlp ──► faster-whisper ──► claude -p (read-only) ──► verdict, back in your save spot
(Todoist, a note,   audio +    transcript on      web research + your PC's
 Raindrop, Notion)  caption    your GPU or CPU    current settings
```

1. **Your save spot**, the app you share videos to from your phone (Todoist, Raindrop.io, Notion, or a note file via an iPhone Shortcut), lists the new links. Other apps need a small adapter.
2. **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** downloads the audio and the post's caption: Instagram Reels, TikTok, YouTube Shorts and the many other sites yt-dlp supports.
3. **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)** transcribes it locally, on an NVIDIA GPU when there is one and the CPU otherwise.
4. **[Claude Code](https://docs.claude.com/en/docs/claude-code)** (`claude -p`) researches the claim and inspects the PC's current settings, with a read-only allow-list.
5. The review is posted back next to the video. Failures are marked with the reason, so nothing is retried forever.

## Quick start

You need [Claude Code](https://docs.claude.com/en/docs/claude-code) (signed in) and Python 3.11–3.13. A GPU is optional.

```bash
git clone https://github.com/Scottsdaaale/watch-later
cd watch-later
claude
```

Claude sees it isn't set up yet and offers to do it (or type **`/setup`**, or just say "set this up"). It follows [SETUP.md](SETUP.md): it asks which app you share videos to, connects it, installs Python if needed and everything else, reviews one video as a test, and schedules the nightly run. You only do the parts that have to happen on your phone, plus pasting your app's token into `.env` (Claude never sees it). Every step is also written out if you'd rather do it by hand.

## Save it the way you already do: Share → your app

On the video, tap **Share** and send it to your app, straight from the share sheet. Every source below works that way:

| Your app | Share from the video | Where the review shows up | Status |
|---|---|---|---|
| **Todoist** | Share → Todoist → "Watch Later" project (iPhone, Android) | Comments on the task; moved to "Reviewed" | Tested |
| **Raindrop.io** | Share → Raindrop → a collection (iPhone, Android) | The bookmark's note + a `reviewed` tag | Experimental |
| **Notion** | Share → Notion → a database (iPhone, Android) | Appended to the row's page; Status set | Experimental |
| **A note file** | Share → a "Watch Later" Shortcut that appends to a file in iCloud Drive or Dropbox (iPhone) | A Markdown review next to the file; the line gets ticked off | Tested |
| **Another app in your share sheet** (Telegram, Discord, Slack, Microsoft To Do, email...) | | | Ask Claude to write an adapter: [SETUP.md → Adding a source](SETUP.md#adding-a-source) |

No app yet? Todoist and Raindrop.io are both free and both appear in the share sheet. Instagram's own bookmark ("Saved") can't be read by tools, so use **Share → your app** instead. It's the same number of taps.

## Security

**Read-only, by design.** The review step can look but can't touch. `claude -p` runs with:

- `--permission-mode dontAsk`: anything not explicitly allowed is refused, whatever your default mode is;
- an allow-list of web research plus read-only Windows inspection commands (`reg query`, `powercfg /query`, `nvidia-smi -q`, `systeminfo`, `sc query`…), see `WEB_TOOLS` and `PC_TOOLS` in [watch_later.py](watch_later.py);
- file reading, `Edit`, `Write` and PowerShell blocked; `--setting-sources project` so your personal allow rules don't apply; `--strict-mcp-config` so no MCP servers (mail, task apps...) are connected; and an empty temporary working folder.

If a tip is worth doing, the review gives you the steps and how to undo them. You, or Claude with you watching, apply them.

**Videos are untrusted input.** Anyone can post a reel whose caption or voiceover tries to give an AI instructions ("prompt injection"). watch-later limits what that could achieve:

- Claude **can't read any file**, so nothing on disk (keys, `.env` files, documents) can be read and sent out;
- your source **tokens are never passed to Claude**: they're read from `.env` by watch-later itself, kept out of the environment Claude runs in, and never logged;
- the prompt tells Claude to treat the caption and transcript as data, never as instructions, and to call out videos that try to steer an AI.

What's left: a malicious video *could* try to get Claude to put basic system details it can query (Windows version, hardware, running processes, registry values) into a web request. If that matters to you, set `"inspect_pc": false` in `config.json`: reviews then use web research only and skip the "On this PC" check.

And as with any tip from the internet, read the review before acting on it.

## Commands

```bash
python watch_later.py              # process new videos (what the nightly task runs)
python watch_later.py --dry-run    # review new videos and print them; change nothing in your app
python watch_later.py --url <link> # review one link and print it
python watch_later.py --check      # check libraries, GPU, Claude Code and your source
```

Use the venv's Python: `.\.venv\Scripts\python.exe` on Windows, `.venv/bin/python` elsewhere.

## Configuration

`config.json` (copy [config.example.json](config.example.json)) picks the source and its settings. Secrets live in `.env` (copy [.env.example](.env.example)). Both are gitignored.

| Key | Default | |
|---|---|---|
| `source` | `inbox` | `inbox`, `todoist`, `raindrop` or `notion` |
| `inbox` / `todoist` / `raindrop` / `notion` | | Per-source settings; see each file in [sources/](sources/) |
| `cookies_from_browser` | `""` | `"firefox"` (or `"chrome"`, closed) if Instagram makes yt-dlp log in |
| `whisper_model` / `whisper_cpu_model` | `large-v3-turbo` / `small` | GPU and CPU models |
| `inspect_pc` | `true` | Let reviews run the read-only Windows inspection commands. `false` = web research only |
| `max_per_run` | `10` | Videos per night |
| `claude_timeout_minutes` | `15` | Per video |
| `env_file` | `.env` | Where to read tokens from |

Make the reviews fit what you save by editing the **About the owner** section at the top of [prompt.md](prompt.md).

## Privacy and cost

- Audio and transcription stay on your computer. The transcript, caption and link go to Claude, like any Claude Code session, and the review is posted to your save spot.
- Each video is one `claude -p` run on your Claude plan, so the nightly run uses some of your plan's usage. `max_per_run` caps it.
- Downloading videos is subject to each site's terms. This is meant for personal use on things you saved yourself.

## Development

```bash
python -m unittest discover -s tests -t .
```

The tests use fakes, so they need no tokens, network or GPU.

## License

[MIT](LICENSE)

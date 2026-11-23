"""
watch-later: review the short videos you saved "for later", nightly, on your own PC.

For each new video in your save spot (Todoist, Raindrop.io, Notion, or a Markdown inbox file):
  1. find its link,
  2. download its audio with yt-dlp (plus the post's caption),
  3. transcribe it with faster-whisper (NVIDIA GPU when available, CPU otherwise),
  4. ask Claude Code (`claude -p`, running on this PC) to research the tip and check this PC's
     current settings, read-only,
  5. post the review back next to the video, or mark it as failed with the reason.

Nothing on this PC is ever changed: Claude only gets web research and read-only commands.

Usage:
  python watch_later.py                 # process new videos (what the nightly task runs)
  python watch_later.py --dry-run       # review new videos and print them; change nothing in the source
  python watch_later.py --url <link>    # review one link, print it, touch nothing
  python watch_later.py --check         # check the setup; changes nothing
  python watch_later.py --init-inbox    # create the inbox file (inbox source only)
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from datetime import datetime
from pathlib import Path

from sources import SourceError, load_source
from sources.base import ENV_VALUES, SECRET_NAMES

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.json"
PROMPT_PATH = HERE / "prompt.md"
LOG_DIR = HERE / "logs"

DEFAULTS = {
    "source": "inbox",
    # KEY=value file with your source's token. Relative to this folder. Environment variables win.
    "env_file": ".env",
    # Let the review run read-only Windows inspection commands (reg query, powercfg, ...).
    # false = web research only. See "Security" in README.md.
    "inspect_pc": True,
    "whisper_model": "large-v3-turbo",
    "whisper_cpu_model": "small",
    # e.g. "firefox" or "chrome" if Instagram starts asking for a login. Chrome must be closed
    # for yt-dlp to read its cookies on Windows; Firefox works while open.
    "cookies_from_browser": "",
    "claude_command": "claude",
    "claude_timeout_minutes": 15,
    "max_per_run": 10,
}

# What the review may use. Video captions and transcripts are untrusted (anyone can post a reel
# that says "AI, read this file and visit this URL"), so the review gets web research plus
# read-only inspection commands, and NO file access: nothing on disk can be read and sent out.
# Prefixes are chosen so no allowed command can change a setting. Keep it that way: don't add
# anything that can read files, write, install or reconfigure.
WEB_TOOLS = ["WebSearch", "WebFetch"]
PC_TOOLS = [
    "Bash(reg query:*)",
    "Bash(powercfg /list)",
    "Bash(powercfg /getactivescheme)",
    "Bash(powercfg /query:*)",
    "Bash(powercfg /q:*)",
    "Bash(nvidia-smi -q:*)",
    "Bash(systeminfo)",
    "Bash(bcdedit /enum:*)",
    "Bash(winget list:*)",
    "Bash(tasklist:*)",
    "Bash(sc query:*)",
    "Bash(sc qc:*)",
    "Bash(driverquery:*)",
]
# PowerShell is blocked because Claude Code on Windows prefers it for commands, and its permission
# rules only match whole commands, not the prefixes above; with it gone, Claude uses Bash.
DISALLOWED_TOOLS = ["Edit", "Write", "NotebookEdit", "PowerShell", "Read", "Glob", "Grep"]


def allowed_tools(cfg):
    return WEB_TOOLS + (PC_TOOLS if cfg.get("inspect_pc", True) else [])


def log(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line, flush=True)
    LOG_DIR.mkdir(exist_ok=True)
    with open(LOG_DIR / f"{datetime.now():%Y-%m}.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_config():
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    return cfg


def load_env_file(cfg):
    """Read KEY=value lines into ENV_VALUES (not os.environ, so the Claude subprocess never
    inherits them). Values are never printed."""
    path = Path(cfg.get("env_file") or ".env").expanduser()
    if not path.is_absolute():
        path = HERE / path
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            ENV_VALUES[key] = value


# ── Video → audio + caption ──────────────────────────────────────────────────

def download(url, workdir, cfg):
    """Returns (audio_path, info dict). Raises RuntimeError with a readable reason."""
    import yt_dlp

    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(Path(workdir) / "media.%(ext)s"),
        "quiet": True,
        "noprogress": True,  # keeps the nightly log readable
        "no_warnings": True,
        "noplaylist": True,
        "max_filesize": 300 * 1024 * 1024,
    }
    if cfg.get("cookies_from_browser"):
        opts["cookiesfrombrowser"] = (cfg["cookies_from_browser"],)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = Path(ydl.prepare_filename(info))
    except Exception as e:  # yt-dlp raises many types; its message is the useful part
        msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e))
        if "login" in msg.lower() or "rate-limit" in msg.lower():
            msg += ' (try setting "cookies_from_browser" in config.json)'
        raise RuntimeError(f"Download failed: {msg[:300]}")
    if not path.exists():
        found = list(Path(workdir).glob("media.*"))
        if not found:
            raise RuntimeError("Download produced no file")
        path = found[0]
    return path, info


_model_cache = {}


def add_cuda_dll_dirs():
    """pip's nvidia-cublas/cudnn wheels put their DLLs in site-packages/nvidia/*/bin, which Windows
    doesn't search. Register them so faster-whisper's CUDA backend can load them."""
    if os.name != "nt":
        return
    import site

    for base in site.getsitepackages():
        for bin_dir in Path(base).glob("nvidia/*/bin"):
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


def transcribe(audio_path, cfg):
    add_cuda_dll_dirs()
    # Windows without Developer Mode can't make symlinks; the cache still works, it just warns.
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    from faster_whisper import WhisperModel

    attempts = [("cuda", "float16", cfg["whisper_model"]), ("cpu", "int8", cfg["whisper_cpu_model"])]
    last_error = None
    for device, compute, name in attempts:
        try:
            key = (device, name)
            if key not in _model_cache:
                _model_cache[key] = WhisperModel(name, device=device, compute_type=compute)
            segments, info = _model_cache[key].transcribe(str(audio_path), vad_filter=True)
            text = " ".join(s.text.strip() for s in segments).strip()
            return text, f"{name} on {device}", info.language
        except Exception as e:  # missing CUDA libraries show up here; fall back to CPU
            last_error = e
            log(f"  whisper {name} on {device} failed: {e}")
    raise RuntimeError(f"Transcription failed: {last_error}")


# ── Claude ───────────────────────────────────────────────────────────────────

def claude_exe(cfg):
    """npm installs `claude` as a .cmd shim around claude.exe. Calling the shim sends every
    argument through cmd.exe, which can mangle the `Bash(...:*)` rules, so call the exe."""
    exe = shutil.which(cfg["claude_command"]) or cfg["claude_command"]
    if exe.lower().endswith(".cmd"):
        native = Path(exe).parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
        if native.exists():
            return str(native)
    return exe


def review_with_claude(url, info, transcript, cfg):
    caption = (info.get("description") or "").strip()
    meta = {
        "url": url,
        "creator": info.get("uploader") or info.get("channel") or "",
        "title": info.get("title") or "",
        "duration_seconds": info.get("duration"),
        "posted": info.get("upload_date") or "",
    }
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    prompt += (
        "\n\n---\n\n## The video\n\n"
        f"```json\n{json.dumps(meta, indent=2)}\n```\n\n"
        f"### Caption (from the post)\n\n{caption or '(none)'}\n\n"
        f"### Transcript (Whisper)\n\n{transcript or '(no speech detected)'}\n"
    )
    cmd = [
        claude_exe(cfg), "-p",
        "--output-format", "text",
        # dontAsk refuses anything not allowed below, whatever the default mode is set to.
        "--permission-mode", "dontAsk",
        # Skip user settings so a broad allow rule there can't widen this list, and skip MCP
        # servers (mail, task apps, ...) entirely.
        "--setting-sources", "project",
        "--strict-mcp-config",
        "--allowedTools", *allowed_tools(cfg),
        "--disallowedTools", *DISALLOWED_TOOLS,
    ]
    # Claude Code runs commands through Git Bash on Windows, which rewrites "/v"-style
    # arguments into paths; this keeps `reg query ... /v Name` working.
    env = {k: v for k, v in os.environ.items() if k not in SECRET_NAMES}
    env.update(MSYS_NO_PATHCONV="1", MSYS2_ARG_CONV_EXCL="*")
    # Run from an empty folder so this repo's CLAUDE.md (setup notes) isn't loaded into reviews.
    with tempfile.TemporaryDirectory(prefix="watch-later-claude-") as cwd:
        result = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
            timeout=cfg["claude_timeout_minutes"] * 60, cwd=cwd, env=env,
        )
    review = (result.stdout or "").strip()
    if result.returncode != 0 or not review:
        raise RuntimeError(f"Claude failed (exit {result.returncode}): {(result.stderr or review)[:300]}")
    return review


def review_one(url, cfg):
    with tempfile.TemporaryDirectory(prefix="watch-later-") as tmp:
        log(f"  downloading {url}")
        audio, info = download(url, tmp, cfg)
        log("  transcribing")
        transcript, how, lang = transcribe(audio, cfg)
        log(f"  transcribed {len(transcript)} chars with {how} ({lang})")
    log("  asking Claude")
    review = review_with_claude(url, info, transcript, cfg)
    footer = f"\n\n---\n_watch-later · {datetime.now():%Y-%m-%d} · transcribed with {how}_"
    return review + footer, transcript


# ── The nightly run ──────────────────────────────────────────────────────────

def run(cfg, dry_run, source=None):
    src = source or load_source(cfg, dry_run)
    items = src.fetch_new()
    log(f"{len(items)} new video(s) in {src.name}")
    for item in items[: cfg["max_per_run"]]:
        log(f"{item.title[:80]}")
        try:
            if not item.url:
                raise RuntimeError("No link found")
            review, transcript = review_one(item.url, cfg)
            if dry_run:
                print("\n" + review + "\n")
                continue
            src.post_review(item, review, transcript)
            log("  reviewed")
        except Exception as e:
            reason = str(e) if isinstance(e, RuntimeError) else f"{type(e).__name__}: {e}"
            log(f"  FAILED: {reason}")
            if os.environ.get("WATCH_LATER_DEBUG"):
                traceback.print_exc()
            if not dry_run:
                try:
                    src.mark_failed(item, reason)
                except Exception as e2:  # keep going with the next video
                    log(f"  couldn't mark it as failed: {e2}")


def check(cfg):
    """Setup check: libraries, GPU, claude on PATH, and the source. Changes nothing."""
    ok = True
    add_cuda_dll_dirs()
    try:
        import ctranslate2, yt_dlp, faster_whisper  # noqa: F401

        gpus = ctranslate2.get_cuda_device_count()
        print(f"libraries OK; CUDA GPUs visible to Whisper: {gpus}" + ("" if gpus else " (will use CPU)"))
    except Exception as e:
        ok = False
        print(f"libraries: {e}")
    if shutil.which(cfg["claude_command"]):
        print(f"claude: found ({claude_exe(cfg)})")
    else:
        ok = False
        print("claude: not on PATH (install Claude Code and sign in once by running `claude`)")
    try:
        print(load_source(cfg, dry_run=True).check())
    except SourceError as e:
        ok = False
        print(f"source ({cfg.get('source')}): {e}")
    except Exception as e:
        ok = False
        print(f"source ({cfg.get('source')}): {type(e).__name__}: {e}")
    return ok


def main():
    # Reviews contain emoji; the Windows console (and Task Scheduler) default to a code page
    # that can't print them.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="review new videos and print them; change nothing in the source")
    ap.add_argument("--url", help="review a single link and print it")
    ap.add_argument("--check", action="store_true", help="check the setup; changes nothing")
    ap.add_argument("--init-inbox", action="store_true", help="create the inbox file (inbox source)")
    args = ap.parse_args()
    cfg = load_config()
    load_env_file(cfg)
    if args.check:
        sys.exit(0 if check(cfg) else 1)
    if args.init_inbox:
        src = load_source(dict(cfg, source="inbox"))
        src.create()
        print(f"Inbox ready: {src.path}")
        return
    if args.url:
        review, _ = review_one(args.url, cfg)
        print("\n" + review)
        return
    try:
        run(cfg, args.dry_run)
    except SourceError as e:
        log(f"source problem: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

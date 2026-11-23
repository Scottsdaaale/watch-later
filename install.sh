#!/usr/bin/env bash
# One-time install for watch-later on macOS / Linux:   bash install.sh
# Creates a venv here, installs the libraries, runs the setup check, and prints the line to
# schedule the nightly run. (Windows: use install.ps1.)
# Note: the review's "check this computer" commands are Windows ones; on macOS/Linux the reviews
# still research each tip, they just won't inspect your settings.
set -euo pipefail
cd "$(dirname "$0")"

PY=""
for v in 3.13 3.12 3.11 3.10; do
  if command -v "python$v" >/dev/null 2>&1; then PY="python$v"; break; fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10-3.13 isn't installed (3.14 is too new for the Whisper libraries)." >&2
  exit 1
fi

[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
echo "Installing yt-dlp, faster-whisper, todoist-api-python..."
.venv/bin/python -m pip install --quiet --upgrade -r requirements.txt

command -v claude >/dev/null 2>&1 || echo "warning: 'claude' (Claude Code) isn't on PATH. Install it and run 'claude' once to sign in." >&2

echo "Checking the setup (changes nothing)..."
.venv/bin/python watch_later.py --check

mkdir -p logs
echo
echo "To run nightly at 02:30, add this line with 'crontab -e':"
echo "  30 2 * * * cd '$PWD' && .venv/bin/python watch_later.py >> logs/cron.log 2>&1"
echo "(On a Mac that sleeps at night, cron skips missed runs; SETUP.md has a launchd alternative.)"

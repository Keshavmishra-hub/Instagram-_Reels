#!/usr/bin/env bash
# One-command setup for ReelForge on macOS / Linux (Windows: use WSL2).
#   ./setup.sh            core install + local voice model (~350 MB)
#   ./setup.sh --asr      also the offline speech recogniser used by QC (~460 MB)
set -euo pipefail
cd "$(dirname "$0")"

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1 - $2"; exit 1; }; }
need python3 "install Python 3.10+ (https://www.python.org/downloads/)"
need node    "install Node.js 18+ (https://nodejs.org/)"
need npm     "comes with Node.js"
need ffmpeg  "install FFmpeg (macOS: brew install ffmpeg, Ubuntu: sudo apt install ffmpeg)"

python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    sys.exit("Python 3.10+ is required")
PY

echo "==> Python environment (.venv)"
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -r requirements.txt
if [[ "${1:-}" == "--asr" ]]; then pip install -r requirements-asr.txt; fi

echo "==> Renderer (Remotion)"
(cd renderer && npm install --no-audit --no-fund)

echo "==> Models"
python -m reelforge setup-models ${1:-}

[[ -f .env ]] || cp .env.example .env
echo
python -m reelforge doctor
echo
echo "Done. Start the studio with:  . .venv/bin/activate && python -m reelforge serve   (http://127.0.0.1:8000)"

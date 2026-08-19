#!/usr/bin/env bash
# Orbital Sentinel launcher.  First run: ./run.sh --setup
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$ROOT/backend/.venv/bin/python"
[ -x "$PY" ] || PY="$ROOT/backend/.venv/Scripts/python.exe"
PORT="${PORT:-8712}"

if [[ "${1:-}" == "--setup" ]] || [ ! -x "$PY" ]; then
  python3 -m venv "$ROOT/backend/.venv"
  PY="$ROOT/backend/.venv/bin/python"; [ -x "$PY" ] || PY="$ROOT/backend/.venv/Scripts/python.exe"
  "$PY" -m pip install -q --upgrade pip
  "$PY" -m pip install -q -r "$ROOT/backend/requirements.txt"
  (cd "$ROOT/backend/app" && "$PY" fetch_data.py && "$PY" build_assets.py)
fi

if [[ "${1:-}" == "--train" ]]; then
  (cd "$ROOT/backend/app" && "$PY" train.py)
fi

echo "Serving on http://127.0.0.1:$PORT"
exec "$PY" -m uvicorn main:app --app-dir "$ROOT/backend/app" --host 127.0.0.1 --port "$PORT"

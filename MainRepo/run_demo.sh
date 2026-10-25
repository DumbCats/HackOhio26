#!/usr/bin/env bash
# One command for the demo: build the DB and frontend if missing, then serve everything on :8000.
#   ./run_demo.sh            -> http://localhost:8000/?demo=1
set -euo pipefail
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
[ -d .venv ] || $PY -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
[ -f .env ] || { cp .env.example .env; echo "Created .env: set CONCIERGE_SALT to the team's shared salt"; }
[ -e aep-challenge/data/raw/Data1.zip ] || { echo "Raw data missing: run 'git submodule update --init' (or link aep-challenge)"; exit 1; }
[ -f data/outage_concierge.db ] || python -m ingest.build_db
if [ ! -d frontend/dist ]; then (cd frontend && npm install --no-audit --no-fund && npm run build); fi
echo "Open http://localhost:8000/?demo=1"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log

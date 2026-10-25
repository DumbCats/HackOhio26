"""Shared settings (contracts/API.md section 5). Every lane imports constants from here."""
import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

_db = Path(os.environ.get("CONCIERGE_DB") or "data/outage_concierge.db")
DB_PATH = _db if _db.is_absolute() else REPO_ROOT / _db

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY") or None
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or None
GEMINI_MODEL = os.environ.get("GEMINI_MODEL") or "gemini-flash-latest"  # alias: pinned names get retired

REPLAY_SEED = 8
MC_SEED = 42
REGIONAL_CREWS = 150
DEFAULT_SEVERITY = 0.8

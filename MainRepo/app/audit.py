"""Audit trail (MASTER_PLAN N11): one JSON line per API response or chat turn in logs/audit.jsonl.

Logged: time, endpoint, query params (minus `needs`), status, response `source`, seeds, chat
tools used and safety flag. Never logged: chat text, declared needs, request bodies.
"""
from __future__ import annotations

import json
import threading
import time

from app import config

LOG_PATH = config.REPO_ROOT / "logs" / "audit.jsonl"
DROP_PARAMS = {"needs"}
_lock = threading.Lock()


def write(entry: dict) -> None:
    entry = {"ts": round(time.time(), 3), "replay_seed": config.REPLAY_SEED, "mc_seed": config.MC_SEED, **entry}
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _lock, open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")
    except OSError:
        pass  # auditing must never break a response


def params(query: dict) -> dict:
    return {k: v for k, v in query.items() if k not in DROP_PARAMS}

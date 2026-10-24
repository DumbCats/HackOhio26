"""Shared helpers for Lane B (models + rag).

Uses Lane D's app.config / app.db when they exist; otherwise falls back to the
same defaults the contract specifies, so Lane B runs before Lane D lands.
"""
from __future__ import annotations

import json
import os
import sqlite3
from functools import lru_cache
from pathlib import Path

try:  # Lane D owns app/config.py
    from app.config import DB_PATH, MC_SEED, REGIONAL_CREWS, DEFAULT_SEVERITY, REPO_ROOT  # type: ignore
except ImportError:
    REPO_ROOT = Path(__file__).resolve().parents[2]
    DB_PATH = Path(os.environ.get("CONCIERGE_DB", REPO_ROOT / "data" / "outage_concierge.db"))
    MC_SEED = 42
    REGIONAL_CREWS = 150
    DEFAULT_SEVERITY = 0.8

MOCKS_DIR = REPO_ROOT / "contracts" / "mocks"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"   # committed model weights (no raw data)
CACHE_DIR = REPO_ROOT / "data" / "model_cache"                  # gitignored per-home caches
OUTAGE_LINK = "https://www.appalachianpower.com/outages/"

COMMON_MISSING_DATA = [
    "No live weather data",
    "No real crew data",
    "Past repair records have dates but no times",
]


class UnknownHome(KeyError):
    """Raised for a home_id not in the DB. Routes turn it into HTTP 404."""


def get_conn() -> sqlite3.Connection:
    try:  # Lane D owns app/db.py
        from app.db import get_conn as d_get_conn  # type: ignore
        return d_get_conn()
    except ImportError:
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn


@lru_cache(maxsize=None)
def load_mock(name: str) -> dict:
    with open(MOCKS_DIR / name, encoding="utf-8") as f:
        return json.load(f)


# --- Damage history with the circuit fix (MASTER_PLAN A9, A12) -------------------
# Rohit's DB stores ARCOS 'CIRnn' as '00000nn', which is wrong for 2-16. Until Lane A
# lands the fix, Lane B reads the raw ARCOS table (read-only) and converts here.

ARCOS_ZIP = REPO_ROOT / "aep-challenge" / "data" / "raw" / "Data1.zip"
ARCOS_DBF = "arcos_prod_damage_09_28_Clip.dbf"
CROSSWALK_PATH = REPO_ROOT / "ingest" / "circuit_crosswalk.json"

# Storm windows by report date (DATA_FACTS §4, prototype final.py)
FEB2025 = ("2025-02-12", "2025-02-18")
SEP2024 = ("2024-09-26", "2024-10-02")
STORM_START_DATE = "2025-02-13"   # t = 0 (A1)
# A9 bulk close-out of the Sep 2024 storm. Oct 23 (25 rows, all 25-26 days) is the same
# batch spilling into a second day; A9 names only Oct 22. Flagged to the team.
BULK_CLOSEOUT_DATES = {"2024-10-22", "2024-10-23"}


def _iso(yyyymmdd: str) -> str | None:
    s = str(yyyymmdd).strip().split(".")[0]
    if len(s) != 8 or not s.isdigit():
        return None
    return f"{s[:4]}-{s[4:6]}-{s[6:]}"


@lru_cache(maxsize=1)
def cir_to_customer_circuit() -> dict[int, str]:
    """ARCOS CIR number -> customer 7-digit circuit_id (inverse of the crosswalk)."""
    with open(CROSSWALK_PATH, encoding="utf-8") as f:
        xw = json.load(f)["map"]
    return {int(cir): f"{int(cust):07d}" for cust, cir in xw.items()}


def storm_of(report_date: str) -> str:
    if FEB2025[0] <= report_date <= FEB2025[1]:
        return "feb2025"
    if SEP2024[0] <= report_date <= SEP2024[1]:
        return "sep2024"
    return "other"


@lru_cache(maxsize=1)
def damage_history() -> tuple[dict, ...]:
    """All ARCOS rows on a CIR circuit, with the corrected 7-digit circuit_id.

    Each row: circuit_id, storm, report_date, repaired_date (ISO or None), repaired (bool),
    asset_type, access_issue (bool), special_equipment, lat, lon, repair_days
    (None when excluded from duration stats by A9). Coordinates stay in the backend.
    """
    from datetime import date
    from ingest.dbf_reader import DbfReader  # read-only use of Rohit's reader

    xw = cir_to_customer_circuit()
    rows = []
    for batch in DbfReader(str(ARCOS_ZIP), ARCOS_DBF).stream_records(batch_size=5000):
        for r in batch:
            circ = str(r.get("Circuit", "")).strip().upper()
            if not (circ.startswith("CIR") and circ[3:].isdigit()):
                continue  # A12: drop non-CIR rows
            cid = xw.get(int(circ[3:]))
            rep = _iso(r.get("Report_Tim", ""))
            if cid is None or rep is None:
                continue
            fixed = _iso(r.get("Repaired_D", ""))
            repaired = str(r.get("Repaired", "")).strip().lower() == "yes"
            days = None
            if repaired and fixed and fixed not in BULK_CLOSEOUT_DATES:  # A9 exclusions
                days = (date.fromisoformat(fixed) - date.fromisoformat(rep)).days
            rows.append({
                "circuit_id": cid,
                "storm": storm_of(rep),
                "report_date": rep,
                "repaired_date": fixed,
                "repaired": repaired,
                "asset_type": str(r.get("Asset_Type", "")).strip() or "primary",
                "access_issue": str(r.get("Access_Iss", "")).strip().lower() == "yes",
                "special_equipment": str(r.get("Special_Eq", "")).strip(),
                "lat": float(r.get("Latitude") or 0.0),
                "lon": float(r.get("Longitude") or 0.0),
                "repair_days": days,
            })
    return tuple(rows)

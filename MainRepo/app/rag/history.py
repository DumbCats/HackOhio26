"""Privacy-safe history counts for the line (circuit) that serves a home.

Only counts and plain words leave this module: never circuit ids, device ids,
coordinates or row-level records. Uses app.models.common.damage_history() (the
corrected circuit ids, MASTER_PLAN A12), never damage_events.circuit_id.

No peeking (A5/A13): only damage rows whose report day ended before the
storm-clock time t count, and a repair time only counts if the repair date is
also before t.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from datetime import date, datetime, timedelta
from functools import lru_cache

import numpy as np

from app.models.common import (
    COMMON_MISSING_DATA,
    STORM_START_DATE,
    UnknownHome,
    damage_history,
    get_conn,
)

MIN_ROWS = 3          # suppress anything computed from fewer rows
MIN_REPAIR_ROWS = 5   # repair-time stats (median + day buckets) need at least this many rows
MIN_RANGE_ROWS = 10   # a P10-P90 repair range needs at least this many rows
N_SIMILAR = 5         # "lines like yours"
HOME_ID_RE = re.compile(r"^p_[0-9a-f]{16}$")
NOT_ENOUGH = "not enough history"

ASSET_WORDS = {
    "primary": "damaged main power line",
    "Pole": "broken pole",
    "Fuse Bank": "blown fuse equipment",
    "secondary": "damaged line near homes",
    "Transformer": "damaged transformer",
    "Recloser Bank": "damaged switching equipment",
    "Switch": "damaged switching equipment",
}
STORM_ORDER = ("sep2024", "feb2025", "other")


def _storm_label(storm: str, t: float) -> str:
    if storm == "feb2025":
        if t >= 0:
            return "this storm so far (February 2025, full days only)"
        return "February 2025 winter storm"
    if storm == "sep2024":
        return "September 2024 storm"
    return "other dates"


def cutoff_date(t: float) -> str:
    """ISO date of the storm-clock time t. Rows count only if reported strictly before it."""
    start = datetime.fromisoformat(STORM_START_DATE)
    return (start + timedelta(hours=float(t))).date().isoformat()


def _fmt(x: float) -> int | float:
    """Round to 1 decimal; return an int when whole (so '1' not '1.0' in text)."""
    r = round(float(x), 1)
    return int(r) if r == int(r) else r


def _days(x) -> str:
    return "day" if x == 1 else "days"


def _repair_stats(days: list[int]) -> dict | None:
    """Repair days from report to fix (dates only).

    < 5 records: None ("not enough history"). 5-9: median + day buckets.
    >= 10: also a P10-P90 range (nearest rank, whole days). Buckets follow MASTER_PLAN A4's
    0 / 1 / 2 / 3+ day split; the text uses cumulative "N of M within ..." counts.
    """
    m = len(days)
    if m < MIN_REPAIR_ROWS:
        return None
    arr = np.asarray(days, dtype=float)
    med = _fmt(np.percentile(arr, 50))
    same = sum(1 for d in days if d <= 0)
    one = sum(1 for d in days if d <= 1)
    two = sum(1 for d in days if d <= 2)
    late = m - two
    out = {
        "records_used": m,
        "median_days": med,
        "fixed_by_day": {"same_day": same, "within_1_day": one, "within_2_days": two,
                         "3_or_more_days": late},
    }
    text = (f"{same} of {m} were fixed the same day they were reported, {one} of {m} within "
            f"1 day, and {two} of {m} within 2 days; {late} of {m} took 3 or more days. "
            f"The middle repair took about {med} {_days(med)}")
    if m >= MIN_RANGE_ROWS:
        lo, hi = (_fmt(v) for v in np.percentile(arr, [10, 90], method="nearest"))
        out["range_days"] = {"low": lo, "high": hi}
        text += f", and 8 in 10 took between {lo} and {hi} {_days(hi)}"
    out["text"] = text + " (dates only, no times)."
    return out


# --- cached per-circuit aggregates ------------------------------------------------

def _premise_columns(conn) -> set[str]:
    return {r[1] for r in conn.execute("PRAGMA table_info(premises)").fetchall()}


@lru_cache(maxsize=1)
def _circuit_static() -> dict[str, dict]:
    """circuit_id -> {homes, avg_upstream, overhead_share|None}. Stays in the backend."""
    # Connection is not closed on purpose: Lane D's app.db.get_conn may hand out a shared one.
    conn = get_conn()
    cols = _premise_columns(conn)
    oh = ", AVG(overhead)" if "overhead" in cols else ", NULL"
    rows = conn.execute(
        "SELECT circuit_id, COUNT(*), AVG(upstream_device_count)" + oh
        + " FROM premises GROUP BY circuit_id").fetchall()
    return {r[0]: {"homes": int(r[1]), "avg_upstream": float(r[2] or 0.0),
                   "overhead_share": (None if r[3] is None else float(r[3]))}
            for r in rows}


@lru_cache(maxsize=256)
def _circuit_history(cut: str) -> dict[str, dict]:
    """circuit_id -> rows reported before `cut` (ISO date), grouped for counting."""
    out: dict[str, dict] = {}
    for r in damage_history():
        if r["report_date"] >= cut:
            continue
        c = out.setdefault(r["circuit_id"], {"n": 0, "storms": Counter(), "types": Counter(),
                                             "access": 0, "repair_days": []})
        c["n"] += 1
        c["storms"][r["storm"]] += 1
        c["types"][ASSET_WORDS.get(r["asset_type"], "other equipment")] += 1
        c["access"] += bool(r["access_issue"])
        # Repair times only from storm records: non-storm work ("other") is scheduled
        # repairs that take weeks and would mislead someone waiting out a storm.
        if (r["storm"] != "other" and r["repair_days"] is not None and r["repaired_date"]
                and r["repaired_date"] < cut):
            c["repair_days"].append(int(r["repair_days"]))
    return out


@lru_cache(maxsize=256)
def _similar_lines(cut: str) -> dict[str, tuple[str, ...]]:
    """circuit_id -> the N_SIMILAR most similar OTHER circuits (standardized features)."""
    static = _circuit_static()
    hist = _circuit_history(cut)
    ids = sorted(static)
    use_oh = all(static[c]["overhead_share"] is not None for c in ids)
    feats = []
    for c in ids:
        s = static[c]
        n = hist.get(c, {}).get("n", 0)
        row = [math.log1p(s["homes"]), s["avg_upstream"], 1000.0 * n / max(s["homes"], 1)]
        if use_oh:
            row.append(s["overhead_share"])
        feats.append(row)
    X = np.asarray(feats, dtype=float)
    sd = X.std(axis=0)
    sd[sd == 0] = 1.0
    Z = (X - X.mean(axis=0)) / sd
    out = {}
    for i, c in enumerate(ids):
        d = np.sqrt(((Z - Z[i]) ** 2).sum(axis=1))
        d[i] = np.inf
        order = sorted(range(len(ids)), key=lambda j: (d[j], ids[j]))  # deterministic ties
        out[c] = tuple(ids[j] for j in order[:N_SIMILAR])
    return out


def _home_circuit(home_id: str) -> str:
    if not isinstance(home_id, str) or not HOME_ID_RE.match(home_id):
        raise UnknownHome(home_id)
    row = get_conn().execute("SELECT circuit_id FROM premises WHERE premise_key = ?",
                             (home_id,)).fetchone()
    if row is None:
        raise UnknownHome(home_id)
    return row[0]


# --- public -----------------------------------------------------------------------

def get_line_history(home_id: str, t: float = 0) -> dict:
    """Privacy-safe past-damage counts for the home's line and for similar lines.

    Raises UnknownHome for an unknown or malformed home_id.
    """
    t = float(t)
    if not math.isfinite(t):
        raise ValueError("t must be a finite number")
    circuit = _home_circuit(home_id)
    cut = cutoff_date(t)
    hist = _circuit_history(cut)
    static = _circuit_static()
    mine = hist.get(circuit, {"n": 0, "storms": Counter(), "types": Counter(),
                              "access": 0, "repair_days": []})
    homes = static.get(circuit, {}).get("homes", 0)
    n = mine["n"]
    summary: list[str] = []

    your_line: dict = {"enough_history": n >= MIN_ROWS}
    if n >= MIN_ROWS:
        by_storm = []
        for s in STORM_ORDER:
            cnt = mine["storms"].get(s, 0)
            if cnt == 0:
                continue
            by_storm.append({"storm": _storm_label(s, t),
                             "count": cnt if cnt >= MIN_ROWS else "fewer than 3"})
        types = [{"type": ty, "count": c}
                 for ty, c in sorted(mine["types"].items(), key=lambda x: (-x[1], x[0]))
                 if c >= MIN_ROWS][:3]
        your_line.update({
            "past_damage_total": n,
            "by_storm": by_storm,
            "common_damage_types": types,
            "access_issues": f"{mine['access']} of {n} past damage records had an access issue noted",
            "typical_repair": _repair_stats(mine["repair_days"]) or NOT_ENOUGH,
            "damage_per_1000_homes": _fmt(1000.0 * n / max(homes, 1)),
        })
        summary.append(f"Your line has {n} past damage records from before this point "
                       f"on the storm clock.")
        for b in by_storm:
            summary.append(f"{b['storm']}: {b['count']}.")
        if types:
            summary.append("Most common: " + ", ".join(f"{x['type']} ({x['count']})"
                                                       for x in types) + ".")
        summary.append(your_line["access_issues"] + ".")
        rep = your_line["typical_repair"]
        summary.append("Past repairs on your line: " + rep["text"] if isinstance(rep, dict)
                       else "Typical repair time on your line: not enough history.")
    else:
        your_line.update({"past_damage_total": None, "note": NOT_ENOUGH})
        summary.append("Your line has not enough history: fewer than 3 past damage "
                       "records before this point on the storm clock.")

    sim_ids = _similar_lines(cut).get(circuit, ())
    sim_n = sum(hist.get(c, {}).get("n", 0) for c in sim_ids)
    sim_days = [d for c in sim_ids for d in hist.get(c, {}).get("repair_days", [])]
    sim_homes = sum(static[c]["homes"] for c in sim_ids)
    lines_like_yours: dict = {
        "lines_compared": len(sim_ids),
        "note": ("Other lines with a similar number of homes, equipment chain and damage "
                 "history, added together and never named."),
    }
    if sim_n >= MIN_ROWS:
        lines_like_yours.update({
            "past_damage_total": sim_n,
            "damage_per_1000_homes": _fmt(1000.0 * sim_n / max(sim_homes, 1)),
            "typical_repair": _repair_stats(sim_days) or NOT_ENOUGH,
        })
        summary.append(f"{len(sim_ids)} lines like yours have {sim_n} past damage records "
                       f"together.")
        rep = lines_like_yours["typical_repair"]
        if isinstance(rep, dict):
            summary.append("Past repairs on those lines: " + rep["text"])
    else:
        lines_like_yours.update({"past_damage_total": None, "typical_repair": NOT_ENOUGH})
        summary.append("Lines like yours: not enough history.")

    return {
        "source": "model_estimate",
        "as_of": f"damage reported before {cut}",
        "your_line": your_line,
        "lines_like_yours": lines_like_yours,
        "summary": summary,
        "assumptions": [
            "Counts come from real AEP damage records (ARCOS) for the line that serves this home.",
            "Only damage reported on days that ended before this point on the storm clock counts.",
            "Repair times use report and repair dates only, so they are in whole days.",
            "Records not marked repaired and a bulk close-out batch are left out of repair times.",
            "Counts from fewer than 3 records are not shown.",
        ],
        "missing_data": list(COMMON_MISSING_DATA) + [
            "No record of damage that was never reported",
        ],
    }

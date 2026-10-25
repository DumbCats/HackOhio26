"""Preparation guidance (MASTER_PLAN N9, N2; contracts/mocks/prep.json).

The bucket comes from the outage length: during an outage from the estimate's P90 (prepare for
the long end of the range); before an outage from the risk band (High -> 24-72 h,
Medium -> 4-24 h, Low -> < 4 h, unknown -> 4-24 h). All text is fixed (app/guidance/text.py).
"""
from __future__ import annotations

import copy

from app.guidance import text
from app.guidance.common import forecast_for, parse_needs, restoration_for

BAND_BUCKET = {"high": "24-72h", "medium": "4-24h", "low": "<4h", "unknown": "4-24h"}


def bucket_for_hours(h: float) -> str:
    if h < 4:
        return "<4h"
    if h < 24:
        return "4-24h"
    if h < 72:
        return "24-72h"
    return "72h+"


def get_prep(home_id: str, t: float = 0, needs: list[str] | None = None, **scenario) -> dict:
    needs = parse_needs(needs)
    r = restoration_for(home_id, t, scenario)
    restored = r.get("restored_at_t") is not None and not r.get("is_out")
    if r.get("is_out"):
        phase = "during"
        est = r.get("estimate")
        bucket = bucket_for_hours(est["p90_h"]) if est else "24-72h"
        why = "your power is out and our estimate's long end is in this range" if est else \
              "your power is out and we can't estimate when it's back"
        actions = [dict(a, when="now") for a in text.DURING[bucket]]
    elif restored:
        phase, bucket = "after", "restored"
        why = "your power is back on"
        actions = [dict(a, when="after") for a in text.AFTER]
    else:
        phase = "before"
        band = forecast_for(home_id, t, scenario)["risk"]["band"]
        bucket = BAND_BUCKET.get(band, "4-24h")
        why = (f"your area is {band.upper()} risk" if band != "unknown"
               else "we can't predict your risk reliably, so we suggest preparing")
        actions = [dict(a, when="before") for a in text.BEFORE[bucket]]

    needs_actions = [{"need": n, "text": text.NEEDS[n][phase]} for n in needs]
    out = {
        "home_id": home_id, "t": t, "source": "fixed_guidance",
        "phase": phase, "duration_bucket": bucket, "why": f"Chosen because {why}.",
        "emergency_line": text.EMERGENCY_LINE,
        "safety": copy.deepcopy(text.SAFETY),
        "actions": actions,
        "needs_actions": needs_actions,
        "assumptions": ["Guidance is chosen by expected outage length and the needs you told us. "
                        "We don't guess anything about you, and we don't store your needs."],
        "missing_data": [],
        "what_would_change": ["A longer estimate adds more steps to this list."] if phase != "after" else [],
        "fallback": None,
    }
    return out

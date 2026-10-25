"""Pick the demo homes from the feed (MASTER_PLAN Lane A step 3, beats in section 2).

(a) story home: HIGH band at t=-18 (high confidence), out at t ~2-6, a second repair on its
    path reported a few hours later that moves the estimate (R3), back 10-20 h after the
    outage, and the real restore time falls inside the updated range.
(b) second home: MEDIUM band, a shorter outage later in the storm.
(c) fallback home: no past damage on its line (A6 fallback), never out in the replay.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from collections import defaultdict

from app import config
from app.sim.feed import get_feed

DEMO_HOMES = config.REPO_ROOT / "data" / "demo_homes.json"
LABELS = {"story": "Maya's home (story)", "second": "Second home", "fallback": "Home with little history"}


def salt_check() -> str:
    from ingest.hasher import PremiseHasher
    return hashlib.sha256(("check:" + PremiseHasher(salt_path=str(config.REPO_ROOT / ".salt")).salt)
                          .encode()).hexdigest()[:12]


def ceil1(x: float) -> float:
    return math.ceil(x * 10 - 1e-9) / 10


def r3_fires(prev_eta: float, prev_p50: float, new_eta: float) -> bool:
    """R3: absolute ETA (t + p50) moves more than 3 h or more than 25% of the previous wait."""
    d = abs(new_eta - prev_eta)
    return d > 3 or d > 0.25 * max(prev_p50, 0.1)


def _risk():
    from app.models import risk
    return risk, risk._cache()


def pick(max_candidates: int = 250) -> dict:
    from app.models.restoration import get_restoration
    f = get_feed()
    risk, rc = _risk()
    cut = risk.load_artifact()["band_cutoffs"]

    def band_conf(k):
        i = rc["index"].get(k)
        if i is None:
            return "unknown", -1
        s = rc["score"][i] * config.DEFAULT_SEVERITY
        b = "high" if s >= cut["high"] else "medium" if s >= cut["medium"] else "low"
        return b, rc["conf"][i]

    groups: dict = defaultdict(list)
    for i, ivs in f.intervals.items():
        if len(ivs) != 1:
            continue
        a, b = ivs[0]
        if not (2 <= a <= 6 and 10 <= b - a <= 20):
            continue
        js = f.home_jobs[i]
        later = [j["report_t"] for j in js if a + 1.5 <= j["report_t"] <= a + 9]
        if len(js) < 2 or not later:
            continue
        groups[(f.circuit[i], tuple(f.paths[i]))].append(i)

    cands = []
    for (_, _), members in groups.items():
        k = f.keys[members[0]]
        band, conf = band_conf(k)
        if band != "high" or conf != risk.CONF_HIGH:
            continue
        cands.append(members[0])
    cands = sorted(cands, key=lambda i: abs(f.intervals[i][0][0] - 4.3))[:max_candidates]

    best = None
    for i in cands:
        k = f.keys[i]
        a, b = f.intervals[i][0]
        r2 = max(j["report_t"] for j in f.home_jobs[i] if a + 1.5 <= j["report_t"] <= a + 9)
        first = get_restoration(k, t=a).get("estimate")
        upd = get_restoration(k, t=r2).get("estimate")
        if not first or not upd:
            continue
        if not r3_fires(a + first["p50_h"], first["p50_h"], r2 + upd["p50_h"]):
            continue
        if not (r2 + upd["p10_h"] <= b <= r2 + upd["p90_h"]):
            continue
        first_missed = b > a + first["p90_h"]
        score = (0 if first_missed else 1, abs(a - 4.3) + 0.2 * abs((b - a) - 14))
        if best is None or score < best[0]:
            best = (score, i, a, r2, b)
    if best is None:
        raise RuntimeError("no home matches the story profile")
    _, si, a, r2, b = best
    story = {"home_id": f.keys[si], "label": LABELS["story"], "out_t": round(a, 2),
             "update_t": round(r2, 2), "restored_t": round(b, 2)}

    # (b) second home: medium band, a shorter single outage later on
    second = None
    for i, ivs in sorted(f.intervals.items(), key=lambda kv: kv[1][0][0]):
        a2, b2 = ivs[0]
        if len(ivs) == 1 and 20 <= a2 <= 40 and 3 <= b2 - a2 <= 10 and f.paths[i]:
            band, conf = band_conf(f.keys[i])
            if band == "medium" and conf == risk.CONF_HIGH:
                second = {"home_id": f.keys[i], "label": LABELS["second"]}
                break

    # (c) fallback home: no history on its line, network match, never out, visible cell
    from app.sim.mapcells import _cells
    visible = {c["cell_id"] for c in _cells()[0]}
    fallback = None
    for i, k in enumerate(f.keys):
        if i in f.intervals or not f.paths[i] or f.cell[i] not in visible:
            continue
        if f.circuit_homes[f.circuit[i]] < 200:
            continue
        if band_conf(k)[1] == risk.CONF_FALLBACK_NO_HISTORY:
            fallback = {"home_id": k, "label": LABELS["fallback"]}
            break
    return {"salt_check": salt_check(), "story": story, "second": second, "fallback": fallback}


def write(path=DEMO_HOMES) -> dict:
    homes = pick()
    os.makedirs(path.parent, exist_ok=True)
    path.write_text(json.dumps(homes, indent=2) + "\n", encoding="utf-8")
    return homes


def load() -> dict:
    """demo_homes.json if it matches this DB (same salt), else pick live (slower first call)."""
    global _live
    try:
        homes = json.loads(DEMO_HOMES.read_text(encoding="utf-8"))
        f = get_feed()
        if homes.get("story", {}).get("home_id") in f.index:
            return homes
    except (OSError, ValueError):
        pass
    if _live is None:
        _live = pick()
    return _live


_live = None

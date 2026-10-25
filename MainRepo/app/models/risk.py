"""Lane B risk forecast: `get_forecast` and `get_band` (contracts/API.md §5, mocks forecast*.json).

Score = A5 circuit past-damage term + a sign-constrained L2 logistic regression trained on
the Sep 2024 storm only (app/models/train_risk.py, RISK_MODEL.md), scored with history from
damage before the Feb 2025 storm. Bands per A5, confidence and
fallback per A6. Per-home scores live in the gitignored data/model_cache/ and are built on
first use. Output never contains ids, coordinates, circuit/device ids or percents.
"""
from __future__ import annotations

import copy
import hashlib
import json
from functools import lru_cache

import numpy as np

from app.models import risk_features as rf
from app.models.common import (ARTIFACTS_DIR, CACHE_DIR, COMMON_MISSING_DATA, DB_PATH,
                               DEFAULT_SEVERITY, OUTAGE_LINK, UnknownHome, load_mock)

ARTIFACT = ARTIFACTS_DIR / "risk_model.json"
SCORE_CACHE = CACHE_DIR / "risk_scores.npz"
SERVE_TARGET = "feb2025"

# A6
CONF_FALLBACK_NO_TOPO, CONF_FALLBACK_NO_HISTORY, CONF_LOW, CONF_HIGH = 0, 1, 2, 3
HIGH_MIN_ROWS = 3

# factor strength thresholds on |coef x standardised value| (std units of the score)
STRONG, MEDIUM = 0.5, 0.2
MIN_FACTOR = 0.03   # contributions smaller than this are not worth showing

# feature -> (label when the home's value is HIGH vs other homes, label when it is LOW).
# The label says what is true about the home; "direction" says which way the model moves
# risk because of it (from the sign of coef x standardised value). No numbers in labels.
FACTOR_LABELS = {
    "circ_dmg_per1k": ("Lines near you were damaged often in past storms",
                       "Lines on your circuit were rarely damaged in past storms"),
    "near_dmg": ("Past storms caused damage close to your home",
                 "Past storms caused little damage close to your home"),
    "path_prior_hits": ("Equipment that feeds your home was damaged in a past storm",
                        "Equipment that feeds your home has not been damaged in past storms"),
    "overhead": ("Your power comes through overhead lines, which ice and trees can hit",
                 "Your power comes through underground lines, which storms reach less often"),
    "path_len": ("Your home is far down the line, behind several pieces of equipment",
                 "Your home is close to the start of the line, with little equipment in between"),
    "section_size": ("Your home is on a main stretch of line shared by many homes",
                     "Your home is on a short branch line shared by few homes"),
    "circ_oh_share": ("Most of your circuit runs on overhead lines",
                      "Much of your circuit runs underground"),
    "circ_size": ("Your circuit is large and covers a lot of ground",
                  "Your circuit is small and covers less ground"),
    "pole_density": ("You live in a built-up area with many poles close together",
                     "You live in a more spread-out area with fewer poles nearby"),
    "pole_wood_share": ("Most poles near you are wood",
                        "Fewer poles near you are wood than in most areas"),
    "pole_age": ("Poles near you are older than in most areas",
                 "Poles near you are newer than in most areas"),
}


# ------------------------------------------------------------- scoring ----------
@lru_cache(maxsize=1)
def load_artifact() -> dict:
    with open(ARTIFACT, encoding="utf-8") as f:
        return json.load(f)


def _z(feat: dict, art: dict) -> np.ndarray:
    X = rf.design_matrix(feat, art["serve_target"])
    mu, sd = np.array(art["serve_mean"]), np.array(art["serve_std"])
    bad = ~np.isfinite(X)
    X[bad] = np.take(mu, np.nonzero(bad)[1])
    return (X - mu) / sd


def served_scores(feat: dict, art: dict) -> np.ndarray:
    """Positive per-home score (higher = riskier) for the served candidate."""
    z = _z(feat, art)
    hybrid = np.exp(z @ np.array(art["coef"]))
    if art.get("served") == "baseline":   # A5 heuristic won the backtest: rank by it, hybrid breaks ties
        return feat[f"baseline_{art['serve_target']}"] + 1e-6 * hybrid
    if art.get("served") == "learned":
        return 1.0 / (1.0 + np.exp(-(z @ np.array(art["learned_coef"]) + art["learned_intercept"])))
    return hybrid


CACHE_VERSION = "3"


def _artifact_sig() -> str:
    """Cache key: artifact content + cache layout version (+ feature cache mtime)."""
    h = hashlib.sha256(ARTIFACT.read_bytes() + CACHE_VERSION.encode())
    if rf.FEATURES_CACHE.exists():
        h.update(str(rf.FEATURES_CACHE.stat().st_mtime_ns).encode())
    return h.hexdigest()[:16]


def build_cache(verbose: bool = False) -> dict:
    """Score every home and write data/model_cache/risk_scores.npz. Returns count stats."""
    art = load_artifact()
    feat = rf.load_features(verbose=verbose)
    z = _z(feat, art)
    contrib = (z * np.array(art["coef"])).astype(np.float32)
    score = served_scores(feat, art)
    topo = feat["has_topo"].astype(bool)
    rows = feat[f"circ_rows_{art['serve_target']}"]
    conf = np.where(~topo, CONF_FALLBACK_NO_TOPO,
                    np.where(rows <= 0, CONF_FALLBACK_NO_HISTORY,
                             np.where(rows >= HIGH_MIN_ROWS, CONF_HIGH, CONF_LOW))).astype(np.int8)
    # percentile among homes with topology (rank_note)
    pct = np.zeros(len(score))
    s_t = np.sort(score[topo])
    pct[topo] = np.searchsorted(s_t, score[topo], side="left") / max(len(s_t), 1)
    rf.ensure_cache_dir()
    np.savez(SCORE_CACHE, keys=feat["keys"], score=score, contrib=contrib, z=z.astype(np.float32), conf=conf,
             pct=pct, sig=np.array(_artifact_sig()))

    cut = art["band_cutoffs"]
    b = _bands(score * DEFAULT_SEVERITY, cut)
    shown = conf >= CONF_LOW
    circ = feat["circ_index"]
    stats = {
        "homes": int(len(score)),
        "bands_all_homes_with_topology": {k: int(((b == k) & topo).sum()) for k in ("high", "medium", "low")},
        "bands_shown (non-fallback)": {k: int(((b == k) & shown).sum()) for k in ("high", "medium", "low")},
        "confidence_homes": {"high": int((conf == CONF_HIGH).sum()), "low": int((conf == CONF_LOW).sum()),
                             "fallback_no_history": int((conf == CONF_FALLBACK_NO_HISTORY).sum()),
                             "fallback_no_topology": int((conf == CONF_FALLBACK_NO_TOPO).sum())},
        "confidence_circuits": {
            "high": int(len(np.unique(circ[conf == CONF_HIGH]))),
            "low": int(len(np.unique(circ[conf == CONF_LOW]))),
            "fallback_no_history": int(len(np.unique(circ[conf == CONF_FALLBACK_NO_HISTORY]))),
        },
        "fallback_share_of_homes": round(float((conf < CONF_LOW).mean()), 4),
    }
    return stats


def _bands(scaled: np.ndarray, cut: dict) -> np.ndarray:
    return np.where(scaled >= cut["high"], "high", np.where(scaled >= cut["medium"], "medium", "low"))


@lru_cache(maxsize=1)
def _cache() -> dict:
    if not DB_PATH.exists():
        raise RuntimeError(f"database missing at {DB_PATH}; run python -m ingest.build_db")
    ok = False
    if SCORE_CACHE.exists():
        with np.load(SCORE_CACHE, allow_pickle=False) as z:
            ok = str(z["sig"]) == _artifact_sig()
    if not ok:
        build_cache()
    with np.load(SCORE_CACHE, allow_pickle=False) as z:
        d = {k: z[k] for k in z.files}
    d["index"] = {k: i for i, k in enumerate(d["keys"].tolist())}
    d["score"] = d["score"].tolist()
    d["pct"] = d["pct"].tolist()
    d["conf"] = d["conf"].tolist()
    return d


def warm_up() -> None:
    _cache()


def _idx(home_id: str) -> int:
    i = _cache()["index"].get(home_id)
    if i is None:
        raise UnknownHome(home_id)
    return i


def _band_at(score: float, severity: float) -> str:
    cut = load_artifact()["band_cutoffs"]
    s = score * float(severity)
    return "high" if s >= cut["high"] else "medium" if s >= cut["medium"] else "low"


# ------------------------------------------------------------- public API -------
def get_band(home_id: str, severity: float = DEFAULT_SEVERITY) -> str:
    """'low' | 'medium' | 'high' | 'unknown' (A6 fallback)."""
    c = _cache()
    i = _idx(home_id)
    if c["conf"][i] < CONF_LOW:
        return "unknown"
    return _band_at(c["score"][i], severity)


def _storm(t: float, severity: float) -> dict:
    return {"name": "Winter storm", "severity": severity, "hours_until_storm": max(0, -t), "simulated": True}


def _rank_note(pct: float) -> str:
    n = int(pct * 10)
    if n >= 5:
        return f"Higher than about {min(n, 9)} in 10 homes in this area. This is a comparison, not a percent chance."
    m = int((1.0 - pct) * 10)
    if m >= 9:
        return "Lower than most homes in this area. This is a comparison, not a percent chance."
    return f"Lower than about {max(m, 1)} in 10 homes in this area. This is a comparison, not a percent chance."


def _factors(i: int) -> list[dict]:
    """Top 3 features by |coef x standardised value| for this home."""
    c = _cache()
    names = load_artifact()["features"]
    row = c["contrib"][i]
    zrow = c["z"][i]
    order = np.argsort(-np.abs(row), kind="stable")[:3]
    out = []
    for j in order:
        v = float(row[j])
        if abs(v) < MIN_FACTOR:
            continue
        high_label, low_label = FACTOR_LABELS[names[j]]
        out.append({
            "label": high_label if zrow[j] > 0 else low_label,
            "direction": "up" if v > 0 else "down",
            "strength": "strong" if abs(v) >= STRONG else "medium" if abs(v) >= MEDIUM else "weak",
        })
    return out


def _fallback(home_id: str, t: float, severity: float, no_topo: bool) -> dict:
    out = copy.deepcopy(load_mock("forecast_fallback.json"))
    out["home_id"] = home_id
    out["t"] = t
    out["storm"] = _storm(t, severity)
    out["fallback"]["link"] = OUTAGE_LINK
    if no_topo:
        out["risk"]["confidence_reason"] = "We could not match your home to the line map."
        out["missing_data"] = COMMON_MISSING_DATA + ["Your home is not on the line map we have"]
        out["fallback"]["reason"] = "no_topology"
        out["fallback"]["message"] = ("We can't match your home to the line map, so we can't estimate your "
                                      "risk. Prepare as if you could lose power, and check the official outage map.")
        out["what_would_change"] = ["A match between your home and the line map."]
    else:
        out["missing_data"] = COMMON_MISSING_DATA + ["No past storm damage recorded for your line"]
    return out


def get_forecast(home_id: str, t: float = 0, severity: float = DEFAULT_SEVERITY) -> dict:
    c = _cache()
    i = _idx(home_id)
    conf = c["conf"][i]
    if conf < CONF_LOW:
        return _fallback(home_id, t, severity, no_topo=(conf == CONF_FALLBACK_NO_TOPO))

    score = c["score"][i]
    band = _band_at(score, severity)
    missing = list(COMMON_MISSING_DATA)
    if conf == CONF_HIGH:
        confidence, reason, note = "high", "Lines near you have a long record from past storms.", None
    else:
        confidence = "low"
        reason = "Limited history: there are only a few past storm damage records for your line."
        note = "Limited history: treat this band as a rough guide."
        missing.append("Only a little past storm history for your line")

    what = []
    if band != "low":
        what.append("A weaker storm would lower this band.")
    if band != "high":
        what.append("A stronger storm would raise this band." if _band_at(score, 1.0) != band
                    else "Even the strongest storm setting would not raise this band.")
    what.append("Live weather data could raise or lower it.")

    risk = {
        "band": band,
        "headline": f"Your area is {band.upper()} risk for losing power, compared with nearby homes",
        "confidence": confidence,
        "confidence_reason": reason,
        "factors": _factors(i),
        "rank_note": _rank_note(c["pct"][i]),
    }
    if note:
        risk["note"] = note
    return {
        "home_id": home_id,
        "t": t,
        "source": "model_estimate",
        "storm": _storm(t, severity),
        "risk": risk,
        "assumptions": [
            "Risk comes from where damage happened in earlier storms, not live weather.",
            "Risk compares your area with nearby homes; it is not a percent chance.",
        ],
        "missing_data": missing,
        "what_would_change": what,
        "fallback": None,
    }

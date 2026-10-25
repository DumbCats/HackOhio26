"""Lane B risk model: contract shape, privacy, A5 slider monotonicity, A6 fallback, speed."""
import json
import re
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # run from repo root without pytest.ini

from app.models.common import DB_PATH, OUTAGE_LINK, UnknownHome, load_mock  # noqa: E402

pytestmark = pytest.mark.skipif(not DB_PATH.exists(), reason="build the DB first: python -m ingest.build_db")

if DB_PATH.exists():
    from app.models import risk


@pytest.fixture(scope="module")
def cache():
    risk.warm_up()
    return risk._cache()


@pytest.fixture(scope="module")
def sample(cache):
    keys = cache["keys"]
    step = max(1, len(keys) // 400)
    return [str(k) for k in keys[::step]]


def _homes_with(cache, conf_codes, n=50):
    return [str(cache["keys"][i]) for i, c in enumerate(cache["conf"]) if c in conf_codes][:n]


def _keys(d, prefix=""):
    out = set()
    for k, v in d.items():
        out.add(prefix + k)
        if isinstance(v, dict):
            out |= _keys(v, prefix + k + ".")
    return out


def test_shape_matches_mock(cache):
    mock = load_mock("forecast.json")
    for hid in _homes_with(cache, {risk.CONF_HIGH}, 3) + _homes_with(cache, {risk.CONF_LOW}, 3):
        out = risk.get_forecast(hid, t=-18, severity=0.8)
        assert _keys(mock) <= _keys(out)
        assert out["home_id"] == hid and out["t"] == -18
        assert out["source"] == "model_estimate"
        assert out["storm"] == {"name": "Winter storm", "severity": 0.8, "hours_until_storm": 18, "simulated": True}
        r = out["risk"]
        assert r["band"] in {"low", "medium", "high"}
        assert r["confidence"] in {"low", "medium", "high"}
        assert r["headline"] == f"Your area is {r['band'].upper()} risk for losing power, compared with nearby homes"
        assert 1 <= len(r["factors"]) <= 3
        for f in r["factors"]:
            assert set(f) == {"label", "direction", "strength"}
            assert f["direction"] in {"up", "down"} and f["strength"] in {"strong", "medium", "weak"}
            assert not re.search(r"\d", f["label"])
        assert r["rank_note"].endswith("This is a comparison, not a percent chance.")
        assert out["fallback"] is None
        assert out["missing_data"][:3] == load_mock("forecast.json")["missing_data"]


def test_hours_until_storm_never_negative(cache, sample):
    assert risk.get_forecast(sample[0], t=5)["storm"]["hours_until_storm"] == 0


def test_bands_and_privacy(cache, sample):
    for hid in sample:
        out = risk.get_forecast(hid, t=-6, severity=0.8)
        assert out["risk"]["band"] in {"low", "medium", "high", "unknown"}
        body = dict(out)
        body.pop("home_id")
        s = json.dumps(body)
        assert "%" not in s
        assert not re.search(r"\d{5,}", s), "digit run that could be an id"
        assert not re.search(r"\d+\.\d{4,}", s), "float that could be a coordinate"
        assert "critical" not in s.lower() and "life support" not in s.lower()


def test_lower_severity_never_raises_band(cache, sample):
    order = {"low": 0, "medium": 1, "high": 2}
    sevs = [1.0, 0.9, 0.8, 0.6, 0.4, 0.2, 0.0]
    moved = 0
    for hid in sample:
        bands = [risk.get_band(hid, s) for s in sevs]
        if bands[0] == "unknown":
            assert set(bands) == {"unknown"}
            continue
        ranks = [order[b] for b in bands]
        assert ranks == sorted(ranks, reverse=True), (hid, bands)
        moved += ranks[0] != ranks[-1]
        assert risk.get_forecast(hid, severity=0.6)["risk"]["band"] == bands[3]
    assert moved > 0, "the severity slider should move some bands"


def test_band_shares_at_default_severity(cache):
    import numpy as np
    topo = np.array(cache["conf"]) != risk.CONF_FALLBACK_NO_TOPO
    s = np.array(cache["score"])[topo] * 0.8
    cut = risk.load_artifact()["band_cutoffs"]
    assert abs((s >= cut["high"]).mean() - 0.15) < 0.01
    assert abs(((s >= cut["medium"]) & (s < cut["high"])).mean() - 0.25) < 0.01


def test_fallback_home(cache):
    hid = _homes_with(cache, {risk.CONF_FALLBACK_NO_HISTORY}, 1)[0]
    out = risk.get_forecast(hid, t=-18, severity=0.8)
    mock = load_mock("forecast_fallback.json")
    assert _keys(mock) <= _keys(out)
    assert out["risk"]["band"] == "unknown" and out["risk"]["factors"] == [] and out["risk"]["rank_note"] is None
    assert out["fallback"]["link"] == OUTAGE_LINK
    assert set(out["fallback"]) == {"reason", "message", "link"}
    assert risk.get_band(hid) == "unknown"


def test_low_confidence_has_limited_history_note(cache):
    hid = _homes_with(cache, {risk.CONF_LOW}, 1)[0]
    r = risk.get_forecast(hid)["risk"]
    assert r["confidence"] == "low" and "Limited history" in r["confidence_reason"]
    assert r["band"] in {"low", "medium", "high"}


def test_unknown_home():
    with pytest.raises(UnknownHome):
        risk.get_forecast("p_0000000000000000")
    with pytest.raises(UnknownHome):
        risk.get_band("not-a-home")


def test_deterministic(cache, sample):
    for hid in sample[:20]:
        assert risk.get_forecast(hid, t=-3, severity=0.7) == risk.get_forecast(hid, t=-3, severity=0.7)


def test_fast_after_warm_up(cache, sample):
    risk.get_forecast(sample[0])
    t0 = time.perf_counter()
    for hid in sample[:200]:
        risk.get_forecast(hid, t=-18, severity=0.8)
    assert (time.perf_counter() - t0) / 200 < 0.020


def test_artifact_has_no_per_home_data():
    art = json.loads(risk.ARTIFACT.read_text())
    s = json.dumps(art)
    assert "p_" not in s.replace("pole_", "").replace("path_", "").replace("prior_", "")
    assert not re.search(r"\b\d{7}\b", s)
    assert set(art["metrics"]["candidates_test_all_homes"]) == {"baseline", "learned", "hybrid"}

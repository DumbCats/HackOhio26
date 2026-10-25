"""Alert eligibility, channels, escalation and the 4 proactive messages (MASTER_PLAN N1, D3).

Rules (our documented assumptions, not AEP policy, A7):
  R1 pre-storm      band is Medium or High at the forecast moment (t = -18)
  R2 outage         the home's outage starts (feed)
  R3 estimate moved the absolute return time (t + P50) moves > 3 h or > 25% of the last
                    estimate we sent; checked whenever new damage on the home's path is reported
  R4 restored       power is back (feed)
Channels: push by default; SMS when the phone is in low-power mode; offer a call when a medical
need or critical facility is declared and the outage may last over 12 h (P90 > 12).
Message numbers come from Lane B with the default scenario (the what-if sliders change the
estimate card, not what the utility already sent). Messages stay under 60 words.
"""
from __future__ import annotations

from functools import lru_cache

from app import config
from app.guidance.common import forecast_for, parse_needs, restoration_for

FORECAST_T = -18.0
MEDICAL_NEEDS = {"medical_device", "refrigerated_meds", "critical_facility"}
CALL_P90_H = 12.0

RULES = {
    "R1": "Your area is {band} risk for this storm, so you get a pre-storm alert.",
    "R2": "Damage was reported on the line that feeds your home, so you get an outage alert.",
    "R3": "Your estimated return time moved by more than 3 hours (or 25%), so you get an update.",
    "R4": "Your power came back, so you get a restored message.",
}
RULE_NAMES = {"R1": "Pre-storm alert (Medium or High risk)", "R2": "Outage confirmed",
              "R3": "Estimate updated (moved over 3 h or 25%)", "R4": "Power restored"}


def _r3(prev_eta: float, prev_p50: float, new_eta: float) -> bool:
    d = abs(new_eta - prev_eta)
    return d > 3 or d > 0.25 * max(prev_p50, 0.1)


def _range_words(est: dict) -> str:
    h = est["headline"]
    return h[len("Likely back "):] if h.startswith("Likely back ") else h


@lru_cache(maxsize=2048)
def _events(home_id: str, t: float) -> tuple:
    """Message events up to t with the default scenario: tuple of dicts (cached)."""
    from app.sim import feed
    events = []
    fc = forecast_for(home_id, FORECAST_T)
    band = fc["risk"]["band"]
    if band in ("medium", "high") and t >= FORECAST_T:
        events.append({"rule": "R1", "type": "pre_storm", "t": FORECAST_T, "band": band})
    state = feed.home_state(home_id, t)
    out_since = state.get("out_since_t")
    if out_since is None:
        return tuple(events)
    first = restoration_for(home_id, out_since).get("estimate")
    events.append({"rule": "R2", "type": "outage_confirmed", "t": out_since, "estimate": first,
                   "stage": (restoration_for(home_id, out_since).get("status") or {}).get("label")})
    last = first
    last_t = out_since
    end = state.get("restored_at_t") if state.get("restored_at_t") is not None else t
    probes = sorted({j["report_t"] for j in feed.path_jobs(home_id, end) if out_since < j["report_t"] <= end})
    for pt in probes:
        if state.get("restored_at_t") is not None and pt >= state["restored_at_t"]:
            break
        est = restoration_for(home_id, pt).get("estimate")
        if not est or not last:
            continue
        if _r3(last_t + last["p50_h"], last["p50_h"], pt + est["p50_h"]):
            later = pt + est["p50_h"] > last_t + last["p50_h"]
            events.append({"rule": "R3", "type": "estimate_updated", "t": round(pt, 2), "estimate": est,
                           "later": later})
            last, last_t = est, pt
    if state.get("restored_at_t") is not None:
        r = restoration_for(home_id, t)
        events.append({"rule": "R4", "type": "restored", "t": state["restored_at_t"],
                       "recap": r.get("recap")})
    return tuple(events)


def _text(ev: dict, needs: list[str], hours_until: float) -> str:
    kind = ev["type"]
    if kind == "pre_storm":
        msg = (f"A winter storm is expected in about {round(hours_until)} hours. Your area is "
               f"{ev['band'].upper()} risk for losing power compared with nearby homes. Charge devices and "
               "check your prep list in the app. This is an estimate, not a promise.")
        if MEDICAL_NEEDS & set(needs):
            msg += " You told us about a medical need: plan backup power now."
        return msg
    if kind == "outage_confirmed":
        est = ev.get("estimate")
        lead = f"We know your power is out. {ev['stage']}." if ev.get("stage") else "We know your power is out."
        rng = f" Our estimate: back {_range_words(est)}." if est else ""
        return f"{lead}{rng} Stay away from downed lines."
    if kind == "estimate_updated":
        est = ev["estimate"]
        if ev["later"]:
            return (f"Update: more damage was found on your line. New estimate: back {_range_words(est)} "
                "from now. We'll message you if it changes again.")
        return (f"Update: repairs are going faster than expected. New estimate: back {_range_words(est)} "
                "from now. We'll message you if it changes again.")
    if kind == "restored":
        rc = ev.get("recap") or {}
        hrs = rc.get("actual_h")
        span = f" You were out about {max(1, round(hrs))} hours." if hrs else ""
        return (f"Your power is back.{span} Check food in your fridge before eating it. "
                "If it goes out again, report it on the outage page.")
    return ""


def get_alerts(home_id: str, t: float = 0, needs: list[str] | None = None, low_power: bool = False,
               **scenario) -> dict:
    needs = parse_needs(needs)
    t = float(t)
    events = _events(home_id, round(t, 2))
    channel = "sms" if low_power else "push"
    timeline = [{"type": ev["type"], "rule_id": ev["rule"], "t": ev["t"], "channel": channel,
                 "text": _text(ev, needs, -FORECAST_T)} for ev in events if ev["t"] <= t]

    fc = forecast_for(home_id, t, scenario)
    band = fc["risk"]["band"]
    fired_ids = [ev["rule"] for ev in events]
    rules_fired = [{"rule_id": rid, "text": RULES[rid].format(band=band.upper() if band != "unknown" else "")}
                   for rid in fired_ids]
    if band in ("medium", "high") and "R1" not in fired_ids and t < FORECAST_T:
        rules_fired.insert(0, {"rule_id": "R1", "text": RULES["R1"].format(band=band.upper())})

    r_now = restoration_for(home_id, t, scenario)
    est = r_now.get("estimate")
    p90 = est["p90_h"] if est else None
    medical = bool(MEDICAL_NEEDS & set(needs))
    call_offer = bool(medical and r_now.get("is_out") and p90 is not None and p90 > CALL_P90_H)

    channels = [{"channel": "push", "why": "Default for app users"}]
    if low_power:
        channels.append({"channel": "sms", "why": "Works when data is weak or your battery is low"})
    else:
        channels.append({"channel": "sms", "why": "Backup if your phone is in low-power mode or data is weak"})
    if call_offer:
        channels.append({"channel": "call", "why": "You told us about a medical need and the outage may last over 12 hours"})

    escalations = [
        {"trigger": "You told us about a medical need or critical facility and the outage may last over 12 hours",
         "action": "Offer a call from the utility and share local warming or cooling center info.",
         "active": call_offer},
        {"trigger": "Estimated return time moves by more than 3 hours or 25%",
         "action": "Send an estimate-updated message.", "active": "R3" in fired_ids},
        {"trigger": "You describe an emergency in chat (fire, injury, downed line)",
         "action": "Show the 911 message right away and offer a call back.", "active": False},
    ]
    eligible = True  # every customer gets outage + restored messages; R1 only for Medium/High
    if band in ("medium", "high"):
        summary = (f"Yes. You get outage and restored messages, and because your area is {band.upper()} risk "
                   "you also get a pre-storm alert.")
    elif band == "unknown":
        summary = ("Yes, for outage and restored messages. We can't predict your risk reliably, so there is no "
                   "pre-storm alert; check the official outage page during storms.")
    else:
        summary = "Yes, for outage and restored messages. Your area is LOW risk, so no pre-storm alert."

    return {
        "home_id": home_id, "t": t, "source": "model_estimate",
        "eligible": eligible, "eligibility_summary": summary,
        "rules": [{"rule_id": k, "name": v, "fired": k in fired_ids or (k == "R1" and any(
            r["rule_id"] == "R1" for r in rules_fired))} for k, v in RULE_NAMES.items()],
        "rules_fired": rules_fired,
        "channels": channels,
        "timeline": timeline,
        "escalations": escalations,
        "assumptions": ["These alert rules are our documented assumptions, not AEP policy.",
                        "Messages use our default estimate; the what-if sliders don't change what was sent."],
        "missing_data": [] if band != "unknown" else ["Not enough past storm history for your line"],
        "what_would_change": ["New damage on your line can trigger an estimate update."],
        "fallback": None,
    }

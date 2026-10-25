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
from app.guidance import clock
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


def _range_words(est: dict) -> str:
    h = est["headline"]
    return h[len("Likely back "):] if h.startswith("Likely back ") else h


def _when(est: dict, t: float) -> str:
    """'4 to 12 hours (about Thu 8 AM to 4 PM)': hours from now plus the clock window."""
    return f"{_range_words(est)} (about {clock.window(t + est['p10_h'], t + est['p90_h'])})"


def r1_band(home_id: str) -> str:
    """R1 is decided once, at the forecast moment, with the default storm strength."""
    return forecast_for(home_id, FORECAST_T)["risk"]["band"]


@lru_cache(maxsize=2048)
def _events(home_id: str, t: float) -> tuple:
    """Message events up to t with the default scenario, across every outage so far (cached)."""
    from app.models.restoration import update_times
    from app.sim import feed
    events = []
    band = r1_band(home_id)
    if band in ("medium", "high") and t >= FORECAST_T:
        events.append({"rule": "R1", "type": "pre_storm", "t": FORECAST_T, "band": band})
    for out_since, restored_at in feed.outage_intervals(home_id, t):
        r0 = restoration_for(home_id, out_since)
        first = r0.get("estimate")
        events.append({"rule": "R2", "type": "outage_confirmed", "t": out_since, "estimate": first,
                       "stage": (r0.get("status") or {}).get("label")})
        end = restored_at if restored_at is not None else t
        last, last_t = first, out_since
        for pt in update_times(home_id, out_since, end + 1e-6 if restored_at is None else end):
            if pt > t:
                break
            est = restoration_for(home_id, pt).get("estimate")
            if not est or not last:
                continue
            shift = (pt + est["p50_h"]) - (last_t + last["p50_h"])
            events.append({"rule": "R3", "type": "estimate_updated", "t": pt, "estimate": est, "shift_h": shift})
            last, last_t = est, pt
        if restored_at is not None:
            events.append({"rule": "R4", "type": "restored", "t": restored_at,
                           "actual_h": round(restored_at - out_since, 1)})
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
        rng = f" Our estimate: back {_when(est, ev['t'])}." if est else ""
        return f"{lead}{rng} Stay away from downed lines."
    if kind == "estimate_updated":
        est, shift = ev["estimate"], ev["shift_h"]
        hrs = max(1, round(abs(shift)))
        if shift > 0:
            return (f"Update: more damage was found on your line, so it will take about {hrs} hours longer. "
                    f"New estimate: back {_when(est, ev['t'])}.")
        return (f"Update: repairs are going faster, about {hrs} hours sooner than we said. "
                f"New estimate: back {_when(est, ev['t'])}.")
    if kind == "restored":
        return (f"Your power is back. You were out about {max(1, round(ev['actual_h']))} hours. Check food in "
                "your fridge before eating it. If it goes out again, report it on the outage page.")
    return ""


def get_alerts(home_id: str, t: float = 0, needs: list[str] | None = None, low_power: bool = False,
               **scenario) -> dict:
    needs = parse_needs(needs)
    t = float(t)
    events = _events(home_id, round(t, 2))
    channel = "sms" if low_power else "push"
    timeline = []
    for ev in events:
        if ev["t"] > t:
            continue
        msg = {"type": ev["type"], "rule_id": ev["rule"], "t": ev["t"], "channel": channel,
               "text": _text(ev, needs, -FORECAST_T)}
        if "shift_h" in ev:
            msg["shift_h"] = round(ev["shift_h"], 1)  # how much the return time moved (+ later)
        timeline.append(msg)

    band = r1_band(home_id)  # the same band the pre-storm message used
    fired_ids = [ev["rule"] for ev in events]
    rules_fired = []
    for rid in dict.fromkeys(fired_ids):
        rules_fired.append({"rule_id": rid, "text": RULES[rid].format(band=band.upper())})
    r1_pending = band in ("medium", "high") and t < FORECAST_T
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
        "rules": [{"rule_id": k, "name": v, "fired": k in fired_ids,
                   "eligible": k != "R1" or band in ("medium", "high")} for k, v in RULE_NAMES.items()],
        "r1_pending": r1_pending,
        "rules_fired": rules_fired,
        "channels": channels,
        "timeline": timeline,
        "escalations": escalations,
        "assumptions": ["Messages use our standard estimate; the what-if settings don't change what was sent."],
        "missing_data": [] if band != "unknown" else ["Not enough past storm history for your line"],
        "what_would_change": ["New damage on your line can trigger an estimate update."],
        "fallback": None,
    }

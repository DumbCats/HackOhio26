"""Storm clock -> customer wording. t = hours since Thu 13 Feb 2025 00:00 (MASTER_PLAN A1)."""
from __future__ import annotations

import math

DAYS = ["Thu", "Fri", "Sat", "Sun", "Mon", "Tue", "Wed"]


def _parts(t: float) -> tuple[str, int, int]:
    total = int(round(t * 60))
    day = DAYS[(total // 1440) % 7]
    mins = total % 1440
    return day, mins // 60, mins % 60


def clock(t: float) -> str:
    """'Thu 2:15 PM'."""
    day, h, m = _parts(t)
    return f"{day} {h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def hour_label(t: float, up: bool) -> str:
    """Rounded to the hour (down for the early end, up for the late end): 'Thu 2 PM'."""
    t = math.floor(t) if not up else math.ceil(t)
    day, h, _ = _parts(t)
    return f"{day} {h % 12 or 12} {'AM' if h < 12 else 'PM'}"


def window(lo_t: float, hi_t: float) -> str:
    """'Thu 2 PM to 9 PM' or 'Thu 10 PM to Fri 6 AM'."""
    a, b = hour_label(lo_t, False), hour_label(hi_t, True)
    if a == b:
        b = hour_label(hi_t + 1, True)
    if a.split()[0] == b.split()[0]:
        b = " ".join(b.split()[1:])
    return f"{a} to {b}"

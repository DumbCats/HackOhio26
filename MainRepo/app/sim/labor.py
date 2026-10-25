"""Repair hours per damage job (MASTER_PLAN A3, DATA_FACTS section 7).

Hours = install + remove hours for the construction units a repair needs (from the STORMS
labor workbook), plus site adders, times the workbook's Indirect Labor Multiplier (4.5) for
travel and nonproductive time. No noise here; the feed and the Monte Carlo add it.
"""
from __future__ import annotations

ILM = 4.5  # Indirect Labor Multiplier, Install_Labor_HackOHIO.xlsx

# asset type (lowercase ARCOS Asset_Type) -> install + remove hours (DATA_FACTS 7).
# Wire, capacitor and light have no workbook unit, so these are proxies built from the
# closest units (marked UNSURE in DATA_FACTS).
ASSET_HOURS = {
    "primary": 1.129,           # 2 dead-ends + 2 connectors + 3 insulators (proxy)
    "pole": 4.812,              # medium pole + crossarm + guy + 3 insulators
    "fuse bank": 1.240,         # fuse cutout + equipment lead
    "secondary": 0.879,         # secondary attachment + 2 connectors (proxy)
    "transformer": 3.234,       # 25 kVA transformer + cutout + lead
    "recloser bank": 1.954,     # recloser + lead
    "switch": 2.768,            # switch
    "capacitor bank": 2.008,    # lead + 3 cutouts (proxy)
    "light": 0.872,             # bracket (proxy)
    "step transformer": 3.200,  # 833 kVA + lead (proxy)
}
DEFAULT_HOURS = ASSET_HOURS["primary"]  # blank asset type is treated as primary wire

ACCESS_ADDER = 0.5                      # Access_Iss = Yes
# Workbook adders: Backyard 0.5; Remote Location 1.312 (track/off-road machines); Specialized
# Handling 0.5 (transportation, lifting, positioning) for large trucks and handlers.
EQUIPMENT_ADDERS = {
    "backyard bucket": 0.5,
    "track hoe": 1.312, "yard dog": 1.312, "backhoe": 1.312,
    "big bucket": 0.5, "material handler": 0.5, "tandem bucket": 0.5, "tandem line": 0.5,
}


def job_base_hours(asset_type: str, access_issue: bool, special_equipment: str) -> float:
    """Workbook hours + adders, x4.5, no noise (contracts/API.md section 5)."""
    h = ASSET_HOURS.get(str(asset_type or "").strip().lower(), DEFAULT_HOURS)
    if access_issue:
        h += ACCESS_ADDER
    h += EQUIPMENT_ADDERS.get(str(special_equipment or "").strip().lower(), 0.0)
    return round(h * ILM, 4)

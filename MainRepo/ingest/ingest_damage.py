"""
ARCOS historical damage record ingestion and storm tagging.
"""

import json
import os
import sqlite3
from typing import Dict, Any, List, Optional
from ingest.dbf_reader import DbfReader

CROSSWALK_PATH = os.path.join(os.path.dirname(__file__), "circuit_crosswalk.json")


def load_cir_to_customer() -> Dict[int, str]:
    """ARCOS CIR number -> customer 7-digit circuit_id (MASTER_PLAN A12, DATA_FACTS 2)."""
    with open(CROSSWALK_PATH, encoding="utf-8") as f:
        xw = json.load(f)["map"]
    return {int(cir): f"{int(cust):07d}" for cust, cir in xw.items()}


def arcos_to_customer_circuit(raw: str, xw: Dict[int, str]) -> Optional[str]:
    """'CIR10' -> '0000009' via the crosswalk. None for non-circuit rows ('PENN FOREST', ...)."""
    s = str(raw).strip().upper()
    if not (s.startswith("CIR") and s[3:].isdigit()):
        return None
    return xw.get(int(s[3:]))

ASSET_TO_CU = {
    "primary": "ARM",
    "Pole": "POL",
    "Fuse Bank": "XCO",
    "secondary": "SAA",
    "Transformer": "XFR",
    "Recloser Bank": "REC",
    "Switch": "SWI",
    "Capacitor Bank": "EQL",
    "Light": "BKT"
}


def normalize_circuit_id(raw: str) -> str:
    """Normalizes a customer/device 7-digit circuit id. Do NOT use for ARCOS 'CIRnn' (see arcos_to_customer_circuit)."""
    cleaned = str(raw).strip()
    if cleaned.upper().startswith("CIR"):
        cleaned = cleaned[3:]
    try:
        num = int(cleaned)
        return f"{num:07d}"
    except ValueError:
        return cleaned


def tag_storm_event(report_time_str: str) -> str:
    """Classifies damage records into historical replay storm scenarios."""
    cleaned = str(report_time_str).strip()
    if cleaned.startswith("202502"):
        # Winter Storm of Feb 13-17, 2025 (1,223 damage records)
        return "winter_storm_2025"
    elif cleaned.startswith("202409"):
        # September 2024 Wind & Rain Event (173 damage records)
        return "helene_2024"
    else:
        return "default"


def ingest_damage(zip_path: str, conn: sqlite3.Connection):
    reader = DbfReader(zip_path, "arcos_prod_damage_09_28_Clip.dbf")
    cur = conn.cursor()

    xw = load_cir_to_customer()
    dropped = 0
    damage_rows: List[tuple] = []
    circuit_damage_counts: Dict[str, int] = {}
    circuit_substations: Dict[str, str] = {}

    for batch in reader.stream_records(batch_size=5000):
        for rec in batch:
            outage_num = str(rec.get("Outage_Num", "")).split(".")[0]
            if not outage_num or outage_num == "0":
                # Fallback unique identifier if raw Outage_Num is 0
                outage_num = f"dmg_{len(damage_rows) + 1:04d}"

            raw_circuit = str(rec.get("Circuit", "")).strip()
            circuit_id = arcos_to_customer_circuit(raw_circuit, xw)
            if circuit_id is None:
                dropped += 1  # A12: non-CIR rows are not on a customer circuit
                continue
            substation = str(rec.get("Substation", "")).strip()
            asset_type = str(rec.get("Asset_Type", "")).strip()
            cu_cat = ASSET_TO_CU.get(asset_type, "ARM")

            report_time = str(rec.get("Report_Tim", "")).strip()
            repaired_time = str(rec.get("Repaired_D", "")).strip()
            event_tag = tag_storm_event(report_time)

            lat = float(rec.get("Latitude", 0.0) or 0.0)
            lon = float(rec.get("Longitude", 0.0) or 0.0)
            nearest_dist = float(rec.get("NEAR_DIST", 0.0) or 0.0)

            damage_rows.append((
                outage_num,
                event_tag,
                circuit_id,
                substation,
                asset_type,
                cu_cat,
                report_time,
                repaired_time,
                str(rec.get("Status", "")).strip(),
                str(rec.get("Access_Iss", "")).strip(),
                str(rec.get("Special_Eq", "")).strip(),
                lat,
                lon,
                nearest_dist
            ))

            if circuit_id:
                circuit_damage_counts[circuit_id] = circuit_damage_counts.get(circuit_id, 0) + 1
                if substation:
                    circuit_substations[circuit_id] = substation

    cur.executemany("""
        INSERT OR REPLACE INTO damage_events (
            outage_num, event_name, circuit_id, substation, asset_type, cu_category,
            report_time, repaired_time, status, access_issue, special_equipment,
            lat, lon, nearest_dist
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, damage_rows)

    # Pre-seed circuits table with damage event counts
    for circ_id, count in circuit_damage_counts.items():
        sub = circuit_substations.get(circ_id, "")
        cur.execute("""
            INSERT INTO circuits (circuit_id, substation, damage_event_count)
            VALUES (?, ?, ?)
            ON CONFLICT(circuit_id) DO UPDATE SET
                damage_event_count = excluded.damage_event_count,
                substation = CASE WHEN circuits.substation IS NULL OR circuits.substation = '' THEN excluded.substation ELSE circuits.substation END
        """, (circ_id, sub, count))

    conn.commit()
    print(f"Ingested {len(damage_rows):,} ARCOS damage records across {len(circuit_damage_counts)} circuits "
          f"(dropped {dropped} non-circuit rows).")

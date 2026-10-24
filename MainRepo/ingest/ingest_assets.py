"""
Distribution network protective device asset ingestion.
Loads Fuse Banks, Recloser Banks, Switches, and Transformers into SQLite.
"""

import sqlite3
from typing import List, Tuple
from ingest.dbf_reader import DbfReader
from ingest.ingest_damage import normalize_circuit_id


def ingest_assets(data1_zip: str, data2_zip: str, conn: sqlite3.Connection):
    cur = conn.cursor()
    asset_configs = [
        (data1_zip, "Fuse_Bank_Clip.dbf", "Fuse Bank", "id", "circuit_id", "phase_sett"),
        (data2_zip, "Recloser_Bank_Clip.dbf", "Recloser Bank", "id", "circuit_id", "phase_sett"),
        (data2_zip, "Switch_Clip.dbf", "Switch", "id", "circuit_id", "nominal_vo"),
        (data2_zip, "Transformer_Clip.dbf", "Transformer", "id", "circuit_id", "rated_k_1")
    ]

    total_inserted = 0
    circuit_device_counts = {}

    for zpath, dbf_name, asset_type, id_col, circ_col, sub_col in asset_configs:
        reader = DbfReader(zpath, dbf_name)
        rows: List[Tuple] = []
        for batch in reader.stream_records(batch_size=5000):
            for rec in batch:
                asset_id = str(rec.get(id_col, "")).strip()
                if not asset_id:
                    continue
                raw_circ = str(rec.get(circ_col, "")).strip()
                circ_id = normalize_circuit_id(raw_circ)
                subtype = str(rec.get(sub_col, "")).strip()
                lat = float(rec.get("lat", 0.0) or 0.0)
                lon = float(rec.get("lon", 0.0) or 0.0)

                rows.append((f"{asset_type[:3].lower()}_{asset_id}", asset_type, circ_id, subtype, lat, lon))
                if circ_id:
                    circuit_device_counts[circ_id] = circuit_device_counts.get(circ_id, 0) + 1

            if len(rows) >= 10000:
                cur.executemany("""
                    INSERT OR REPLACE INTO assets (asset_id, asset_type, circuit_id, subtype, lat, lon)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, rows)
                total_inserted += len(rows)
                rows = []

        if rows:
            cur.executemany("""
                INSERT OR REPLACE INTO assets (asset_id, asset_type, circuit_id, subtype, lat, lon)
                VALUES (?, ?, ?, ?, ?, ?)
            """, rows)
            total_inserted += len(rows)

    conn.commit()
    print(f"Ingested {total_inserted:,} distribution protective assets into SQLite.")

"""
Public critical facility ingestion with coordinate conversion and 1km privacy rounding.
Transforms EPSG:3857 Web Mercator to WGS84 and rounds coordinates to ~1.1 km resolution (Brief R17).
"""

import math
import sqlite3
from typing import List, Tuple
from ingest.dbf_reader import DbfReader, read_shp_points


def web_mercator_to_wgs84(x: float, y: float) -> Tuple[float, float]:
    """Converts EPSG:3857 meters to WGS84 degrees (lon, lat)."""
    lon = (x / 6378137.0) * (180.0 / math.pi)
    lat = (2.0 * math.atan(math.exp(y / 6378137.0)) - (math.pi / 2.0)) * (180.0 / math.pi)
    return round(lon, 2), round(lat, 2)  # Rounded to ~1.1 km for privacy


def ingest_facilities(zip_path: str, conn: sqlite3.Connection):
    cur = conn.cursor()
    facility_configs = [
        ("Hospitals_Medic_Pairwis_Clip", "Hospital", "NAME"),
        ("Fire_Stations_E_Pairwis_Clip", "Fire Station", "NAME"),
        ("Ambulance_Servi_Pairwis_Clip", "Ambulance", "NAME")
    ]

    total_inserted = 0
    for file_base, fac_type, name_col in facility_configs:
        reader = DbfReader(zip_path, f"{file_base}.dbf")
        records = []
        for batch in reader.stream_records(batch_size=500):
            records.extend(batch)

        points = read_shp_points(zip_path, f"{file_base}.shp", f"{file_base}.shx")

        rows = []
        for i, rec in enumerate(records):
            if i >= len(points):
                break
            mx, my = points[i]
            lon_approx, lat_approx = web_mercator_to_wgs84(mx, my)

            raw_name = str(rec.get(name_col, rec.get("FACILITY", ""))).strip()
            # Anonymize/mask specific sensitive facility identifiers
            masked_name = f"{fac_type} (Regional Facility #{i + 1})"

            fac_id = f"fac_{fac_type[:3].lower()}_{i + 1:03d}"
            rows.append((fac_id, fac_type, masked_name, lat_approx, lon_approx))

        cur.executemany("""
            INSERT OR REPLACE INTO priority_facilities (facility_id, facility_type, name_masked, lat_approx, lon_approx)
            VALUES (?, ?, ?, ?, ?)
        """, rows)
        total_inserted += len(rows)

    conn.commit()
    print(f"Ingested {total_inserted} priority facilities with privacy coordinate rounding.")

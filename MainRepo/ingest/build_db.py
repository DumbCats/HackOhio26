"""
Master Database Builder for AI Outage Concierge.
Builds the complete SQLite database (data/outage_concierge.db) from challenge raw archives in under 60 seconds.
"""

import os
import sqlite3
import time
import numpy as np
from ingest.hasher import PremiseHasher
from ingest.ingest_labor import ingest_labor
from ingest.ingest_damage import ingest_damage
from ingest.ingest_facilities import ingest_facilities
from ingest.ingest_assets import ingest_assets
from ingest.ingest_premises_and_topology import ingest_premises_and_topology

DEFAULT_DB_PATH = "data/outage_concierge.db"
DEFAULT_DATA1 = "aep-challenge/data/raw/Data1.zip"
DEFAULT_DATA2 = "aep-challenge/data/raw/Data2.zip"
DEFAULT_TOPO = "aep-challenge/data/raw/matched_upstream.zip"
DEFAULT_LABOR = "aep-challenge/data/Install_Labor_HackOHIO.xlsx"


def compute_nearest_damage_distances(conn: sqlite3.Connection):
    """Computes nearest historical damage distance (km) for all premises using vectorized NumPy math."""
    print("Computing nearest damage distances for all premises...")
    cur = conn.cursor()

    # 1. Fetch damage coordinates
    cur.execute("SELECT lat, lon FROM damage_events WHERE lat != 0.0 AND lon != 0.0")
    dmg_points = cur.fetchall()
    if not dmg_points:
        print("  No damage points found, skipping nearest damage distance.")
        return

    dmg_lats = np.array([p[0] for p in dmg_points], dtype=np.float32)
    dmg_lons = np.array([p[1] for p in dmg_points], dtype=np.float32)

    # 2. Fetch premise coordinates and keys
    cur.execute("SELECT premise_key, lat, lon FROM premises")
    premise_data = cur.fetchall()
    if not premise_data:
        return

    keys = [p[0] for p in premise_data]
    p_lats = np.array([p[1] for p in premise_data], dtype=np.float32)
    p_lons = np.array([p[2] for p in premise_data], dtype=np.float32)

    # Vectorized chunked distance
    min_dists = np.empty(len(p_lats), dtype=np.float32)
    chunk_size = 10000

    for i in range(0, len(p_lats), chunk_size):
        chunk_lat = p_lats[i:i + chunk_size, np.newaxis]
        chunk_lon = p_lons[i:i + chunk_size, np.newaxis]

        # Equirectangular approximation: 1 deg lat ~ 111.32 km, 1 deg lon ~ 88.5 km at 37 deg N
        dlat = (chunk_lat - dmg_lats) * 111.32
        dlon = (chunk_lon - dmg_lons) * 88.5
        dists = np.sqrt(dlat ** 2 + dlon ** 2)
        min_dists[i:i + chunk_size] = np.min(dists, axis=1)

    # Batch update premises
    updates = [(float(min_dists[i]), keys[i]) for i in range(len(keys))]
    cur.executemany("UPDATE premises SET nearest_damage_dist_km = ? WHERE premise_key = ?", updates)
    conn.commit()
    print(f"  Updated nearest damage distance for all {len(keys):,} premises.")


def build_database(db_path: str = DEFAULT_DB_PATH):
    t_start = time.time()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            for suffix in ["-wal", "-shm"]:
                if os.path.exists(db_path + suffix):
                    os.remove(db_path + suffix)
        except OSError:
            pass

    print(f"Creating database schema at {db_path}...")
    conn = sqlite3.connect(db_path)

    # Load and execute schema
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    hasher = PremiseHasher()

    # Step 1: Labor Reference
    print("\n[1/5] Ingesting Labor Catalog and Multipliers...")
    ingest_labor(DEFAULT_LABOR, conn)

    # Step 2: ARCOS Damage Records
    print("\n[2/5] Ingesting ARCOS Historical Damage Events...")
    ingest_damage(DEFAULT_DATA1, conn)

    # Step 3: Critical Priority Facilities
    print("\n[3/5] Ingesting Public Critical Facilities (Hospitals, Fire, Ambulance)...")
    ingest_facilities(DEFAULT_DATA1, conn)

    # Step 4: Distribution Protective Assets
    print("\n[4/5] Ingesting Distribution Protective Assets (Fuses, Reclosers, Switches, Transformers)...")
    ingest_assets(DEFAULT_DATA1, DEFAULT_DATA2, conn)

    # Step 5: Premises & Upstream Topology
    print("\n[5/5] Ingesting Customer Premises and Upstream Topology Chains...")
    ingest_premises_and_topology(DEFAULT_DATA1, DEFAULT_TOPO, conn, hasher)

    # Spatial Enhancement: Nearest damage distance
    compute_nearest_damage_distances(conn)

    # Finalize Metadata
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM premises")
    premise_count = cur.fetchone()[0]

    cur.execute("SELECT count(*) FROM damage_events")
    damage_count = cur.fetchone()[0]

    cur.execute("SELECT count(*) FROM circuits")
    circuit_count = cur.fetchone()[0]

    cur.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)", ("db_build_time", str(time.time())))
    cur.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)", ("total_premises", str(premise_count)))
    cur.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)", ("total_damage_events", str(damage_count)))
    cur.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)", ("total_circuits", str(circuit_count)))
    conn.commit()

    conn.close()
    t_end = time.time()
    db_size_mb = os.path.getsize(db_path) / (1024 * 1024)

    print("\n" + "=" * 60)
    print("DATABASE BUILD COMPLETE")
    print(f"Path:            {db_path}")
    print(f"Size:            {db_size_mb:.2f} MB")
    print(f"Total Time:      {t_end - t_start:.2f} seconds")
    print(f"Premises:        {premise_count:,}")
    print(f"Damage Events:   {damage_count:,}")
    print(f"Circuits:        {circuit_count:,}")
    print("=" * 60)


if __name__ == "__main__":
    build_database()

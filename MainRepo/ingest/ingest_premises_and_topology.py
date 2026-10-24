"""
Premises and Upstream Topology Ingestion.
Performs:
1. Streaming of matched_upstream.txt to index upstream protective equipment chains.
2. Streaming of Customer_Clip.dbf and Customer_Clip.shp (point coordinates).
3. Salted SHA-256 premise anonymization (Brief R17).
4. Masking internal equipment IDs into customer-friendly labels (Gap G1).
5. Populating premises and topology_edges tables, plus circuit geographic bounding boxes and counts.
"""

import json
import sqlite3
import zipfile
from typing import Dict, List, Tuple
from ingest.dbf_reader import DbfReader, read_shp_points
from ingest.hasher import PremiseHasher
from ingest.ingest_damage import normalize_circuit_id


def parse_device_token(token: str, step: int, counters: Dict[str, int]) -> Tuple[str, str, str]:
    """
    Parses a token like 'eo_isolating_eqpt_inst*106806731*Recloser (Hydraulic)*...'
    Returns (device_type, device_id, safe_label).
    """
    parts = token.split('*')
    raw_type = parts[0]
    dev_id = parts[1] if len(parts) > 1 else f"dev_{step}"
    subtype = parts[2] if len(parts) > 2 else ""

    if "xfrmr" in raw_type:
        dev_type = "transformer"
        label = "Upstream Transformer"
    elif "isolating" in raw_type:
        sub_lower = subtype.lower()
        if "recloser" in sub_lower:
            dev_type = "recloser"
            counters["recloser"] = counters.get("recloser", 0) + 1
            label = f"Upstream Recloser {counters['recloser']}"
        elif "switch" in sub_lower:
            dev_type = "switch"
            counters["switch"] = counters.get("switch", 0) + 1
            label = f"Upstream Switch {counters['switch']}"
        else:
            dev_type = "fuse"
            counters["fuse"] = counters.get("fuse", 0) + 1
            label = f"Upstream Fuse Cutout {counters['fuse']}"
    elif "circuit" in raw_type:
        dev_type = "circuit_breaker"
        label = "Substation Circuit Breaker"
    else:
        dev_type = "protective_device"
        counters["other"] = counters.get("other", 0) + 1
        label = f"Upstream Protective Device {counters['other']}"

    return dev_type, dev_id, label


def load_topology_map(zip_path: str) -> Dict[str, List[Tuple[str, str, str]]]:
    """
    Loads matched_upstream.txt into an in-memory dictionary.
    Key: premise_nu (raw string) -> Value: List of (device_type, device_id, safe_label)
    """
    topo_map = {}
    print("Reading matched_upstream.txt from zip archive...")
    with zipfile.ZipFile(zip_path) as z:
        with z.open("matched_upstream.txt") as f:
            for line_b in f:
                line = line_b.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                parts = line.split("\t")
                premise_nu = parts[0].strip()
                device_tokens = parts[1:]

                counters: Dict[str, int] = {}
                parsed_chain = []
                for step, tok in enumerate(device_tokens, 1):
                    dev_type, dev_id, label = parse_device_token(tok, step, counters)
                    parsed_chain.append((dev_type, dev_id, label))

                topo_map[premise_nu] = parsed_chain

    print(f"Loaded {len(topo_map):,} topology chains into memory.")
    return topo_map


def ingest_premises_and_topology(
    data1_zip: str,
    topo_zip: str,
    conn: sqlite3.Connection,
    hasher: PremiseHasher
):
    cur = conn.cursor()

    # 1. Load topology in memory
    topo_map = load_topology_map(topo_zip)

    # 2. Load shapefile point coordinates
    print("Reading premise point coordinates from Customer_Clip.shp...")
    points = read_shp_points(data1_zip, "Customer_Clip.shp", "Customer_Clip.shx")
    print(f"Loaded {len(points):,} coordinates.")

    # 3. Stream Customer_Clip.dbf
    print("Streaming Customer_Clip.dbf and inserting into SQLite...")
    reader = DbfReader(data1_zip, "Customer_Clip.dbf")

    premise_rows = []
    topo_edge_rows = []
    circuit_stats: Dict[str, Dict[str, Any]] = {}

    global_idx = 0
    batch_count = 0

    for batch in reader.stream_records(batch_size=10000):
        for rec in batch:
            raw_premise = str(rec.get("premise_nu", "")).strip()
            if not raw_premise:
                raw_premise = str(rec.get("id", global_idx))

            premise_key = hasher.hash_premise(raw_premise)
            raw_circuit = str(rec.get("circuit_id", "UNKNOWN")).strip()
            circuit_id = normalize_circuit_id(raw_circuit)
            xfmr_id = str(rec.get("aep_xfmr_l", "")).strip()

            crit_c = str(rec.get("critical_c", "")).strip().upper()
            spec_op = str(rec.get("special_op", "")).strip()
            is_critical = 1 if (crit_c and crit_c != "N/A") or spec_op else 0

            # Coordinate from shapefile
            lon, lat = points[global_idx] if global_idx < len(points) else (0.0, 0.0)
            global_idx += 1

            # Match topology
            chain = topo_map.get(raw_premise, [])
            device_count = len(chain)
            labels_only = [item[2] for item in chain]
            chain_json = json.dumps(labels_only)

            for step_order, (dev_type, dev_id, safe_label) in enumerate(chain, 1):
                topo_edge_rows.append((premise_key, step_order, dev_type, dev_id, safe_label))

            premise_rows.append((
                premise_key,
                circuit_id,
                xfmr_id,
                is_critical,
                lat,
                lon,
                device_count,
                chain_json,
                0.0  # nearest_damage_dist_km placeholder
            ))

            # Circuit aggregations
            if circuit_id not in circuit_stats:
                circuit_stats[circuit_id] = {
                    "premise_count": 0,
                    "customer_count": 0,
                    "min_lat": lat,
                    "max_lat": lat,
                    "min_lon": lon,
                    "max_lon": lon
                }
            st = circuit_stats[circuit_id]
            st["premise_count"] += 1
            cust_c = rec.get("customer_c", 1) or 1
            st["customer_count"] += int(cust_c)
            if lat != 0.0 and lon != 0.0:
                st["min_lat"] = min(st["min_lat"], lat)
                st["max_lat"] = max(st["max_lat"], lat)
                st["min_lon"] = min(st["min_lon"], lon)
                st["max_lon"] = max(st["max_lon"], lon)

        # Batch insert to keep memory bounded
        cur.executemany("""
            INSERT INTO premises (
                premise_key, circuit_id, transformer_id, is_critical_tier,
                lat, lon, upstream_device_count, upstream_devices_json, nearest_damage_dist_km
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, premise_rows)

        if topo_edge_rows:
            cur.executemany("""
                INSERT INTO topology_edges (premise_key, step_order, device_type, device_id, device_label)
                VALUES (?, ?, ?, ?, ?)
            """, topo_edge_rows)

        conn.commit()
        batch_count += len(premise_rows)
        print(f"  Inserted {batch_count:,} premises...")
        premise_rows = []
        topo_edge_rows = []

    # Update circuits table with aggregated counts and geographic bounding boxes
    for circ_id, st in circuit_stats.items():
        cur.execute("""
            INSERT INTO circuits (circuit_id, premise_count, customer_count, min_lat, max_lat, min_lon, max_lon)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(circuit_id) DO UPDATE SET
                premise_count = excluded.premise_count,
                customer_count = excluded.customer_count,
                min_lat = excluded.min_lat,
                max_lat = excluded.max_lat,
                min_lon = excluded.min_lon,
                max_lon = excluded.max_lon
        """, (circ_id, st["premise_count"], st["customer_count"], st["min_lat"], st["max_lat"], st["min_lon"], st["max_lon"]))

    conn.commit()
    print(f"Successfully inserted all {global_idx:,} premises and updated {len(circuit_stats)} circuits.")

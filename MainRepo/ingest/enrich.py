"""Lane A additions to Rohit's DB (contracts/API.md section 6, MASTER_PLAN A1-A4, A12).

Adds: premises.overhead / cell_id, topology_edges.device_key, the cells table,
damage_events.storm / device_key / report_t / base_hours / priority / homes_affected,
circuits.past_damage / pct_overhead.

Device keys are salted hashes of the topology token's LOC field (the 9-digit ids do not
match the device layers). Coordinates and raw ids stay inside the DB.
"""
from __future__ import annotations

import json
import math
import sqlite3
import zipfile
from collections import Counter, defaultdict
from datetime import date

import numpy as np

from app.sim.labor import job_base_hours
from ingest.fast_readers import read_dbf_columns, read_shp_points
from ingest.hasher import PremiseHasher

REPLAY_SEED = 8                     # app/config.py (kept here so ingest has no app.config dependency)
STORM_T0 = date(2025, 2, 13)        # A1: t = hours since 2025-02-13 00:00
FEB_REPLAY = ("20250213", "20250218")
SEP_STORM = ("20240926", "20241002")
HISTORY_CUTOFF = "20250212"         # "past damage" = reported before the Feb storm window (A5/A6)
NO_OUTAGE_ASSETS = {"Capacitor Bank", "Light"}
MAX_MAP_M = 1000.0                  # damage farther than this from any same-circuit device stays unmapped

CELL_DLAT = 0.009                   # ~1 km
CELL_DLON = 0.0113                  # ~1 km at 37.2 N
MIN_CELL_HOMES = 10

M_PER_DEG_LAT = 111_000.0
M_PER_DEG_LON = 88_500.0


def _add_columns(conn: sqlite3.Connection) -> None:
    adds = {
        "premises": [("overhead", "INTEGER"), ("cell_id", "TEXT")],
        "topology_edges": [("device_key", "TEXT")],
        "damage_events": [("storm", "TEXT"), ("device_key", "TEXT"), ("report_t", "REAL"),
                          ("base_hours", "REAL"), ("priority", "REAL"), ("homes_affected", "INTEGER")],
        "circuits": [("past_damage", "INTEGER DEFAULT 0"), ("pct_overhead", "REAL")],
    }
    for table, cols in adds.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, typ in cols:
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")
    conn.execute("""CREATE TABLE IF NOT EXISTS cells (
        cell_id TEXT PRIMARY KEY, lat_c REAL, lon_c REAL, bounds_json TEXT,
        homes INTEGER, visible INTEGER)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_premises_cell ON premises(cell_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_topo_premise_step ON topology_edges(premise_key, step_order)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_topo_devkey ON topology_edges(device_key)")


def _storm(report: str) -> str:
    if FEB_REPLAY[0] <= report <= FEB_REPLAY[1]:
        return "feb2025"
    if SEP_STORM[0] <= report <= SEP_STORM[1]:
        return "sep2024"
    return "other"


def _to_m(lon, lat):
    return np.stack([np.asarray(lon) * M_PER_DEG_LON, np.asarray(lat) * M_PER_DEG_LAT], axis=-1)


def enrich(conn: sqlite3.Connection, hasher: PremiseHasher, data1: str, data2: str, topo_zip: str) -> dict:
    _add_columns(conn)
    stats: dict = {}

    # ---------------------------------------------------------------- premises
    prem = conn.execute("SELECT premise_key, circuit_id, lat, lon FROM premises").fetchall()
    keys = [r[0] for r in prem]
    idx_of = {k: i for i, k in enumerate(keys)}
    circ = np.array([r[1] for r in prem])
    lat = np.array([r[2] for r in prem], dtype=float)
    lon = np.array([r[3] for r in prem], dtype=float)

    cu = read_dbf_columns(data1, "Customer_Clip.dbf", ["premise_nu", "kind_of_se"])
    overhead: list = [None] * len(keys)
    for pn, kind in zip(cu["premise_nu"], cu["kind_of_se"]):
        i = idx_of.get(hasher.hash_premise(pn))
        if i is not None:
            overhead[i] = 1 if kind == "Overhead" else 0 if kind == "Underground" else None

    # ~1 km grid cells (opaque ids, row-major order)
    lat0 = math.floor(lat.min() / CELL_DLAT) * CELL_DLAT
    lon0 = math.floor(lon.min() / CELL_DLON) * CELL_DLON
    ri = np.floor((lat - lat0) / CELL_DLAT).astype(int)
    ci = np.floor((lon - lon0) / CELL_DLON).astype(int)
    cell_keys = sorted(set(zip(ri.tolist(), ci.tolist())))
    cell_name = {rc: f"c_{n + 1:04d}" for n, rc in enumerate(cell_keys)}
    home_cell = [cell_name[(a, b)] for a, b in zip(ri.tolist(), ci.tolist())]
    counts = Counter(home_cell)
    conn.execute("DELETE FROM cells")
    cell_rows = []
    for (a, b), name in cell_name.items():
        s, w = lat0 + a * CELL_DLAT, lon0 + b * CELL_DLON
        n_, e = s + CELL_DLAT, w + CELL_DLON
        cell_rows.append((name, round((s + n_) / 2, 5), round((w + e) / 2, 5),
                          json.dumps([[round(s, 5), round(w, 5)], [round(n_, 5), round(e, 5)]]),
                          counts[name], int(counts[name] >= MIN_CELL_HOMES)))
    conn.executemany("INSERT INTO cells VALUES (?,?,?,?,?,?)", cell_rows)
    conn.executemany("UPDATE premises SET overhead = ?, cell_id = ? WHERE premise_key = ?",
                     list(zip(overhead, home_cell, keys)))
    stats["cells"] = len(cell_rows)
    stats["cells_visible"] = sum(r[5] for r in cell_rows)

    # ---------------------------------------------------------------- topology chains
    with zipfile.ZipFile(topo_zip) as z:
        text = z.read("matched_upstream.txt").decode("latin1")
    down: Counter = Counter()
    depth: dict = {}
    first_iso: dict = {}
    hashed: dict = {}
    tmp_rows = []
    for line in text.splitlines():
        parts = line.rstrip("\r\n").split("\t")
        if len(parts) < 2:
            continue
        pk = hasher.hash_premise(parts[0].strip())
        toks = [x.split("*") for x in parts[1:]]
        locs = []
        for n_, y in enumerate(toks):
            if len(y) < 4:
                locs.append(None)
            elif y[0] == "eo_circuit":
                locs.append("CB:" + y[3])
            else:
                locs.append(y[3])
        last = len(locs) - 1
        for loc in set(l for l in locs if l is not None):
            down[loc] += 1                      # unique homes behind each device
        for n_, loc in enumerate(locs):
            if loc is None:
                continue
            depth[loc] = min(depth.get(loc, 99), last - n_)   # 0 = breaker
            if loc not in hashed:
                hashed[loc] = hasher.hash_device(loc)
            if pk in idx_of:
                tmp_rows.append((pk, n_ + 1, hashed[loc]))
        if len(toks) >= 2 and len(toks[0]) >= 4:
            iso = [y[3] for y in toks[1:-1] if len(y) >= 4 and y[0] == "eo_isolating_eqpt_inst"]
            first_iso[toks[0][3]] = iso[0] if iso else locs[-1]
    del text
    conn.execute("DROP TABLE IF EXISTS _tmp_devkey")
    conn.execute("CREATE TEMP TABLE _tmp_devkey (premise_key TEXT, step_order INTEGER, device_key TEXT)")
    conn.executemany("INSERT INTO _tmp_devkey VALUES (?,?,?)", tmp_rows)
    conn.execute("CREATE INDEX _tmp_devkey_i ON _tmp_devkey(premise_key, step_order)")
    conn.execute("""UPDATE topology_edges SET device_key = (
        SELECT t.device_key FROM _tmp_devkey t
        WHERE t.premise_key = topology_edges.premise_key AND t.step_order = topology_edges.step_order)""")
    conn.execute("DROP TABLE _tmp_devkey")
    stats["device_keys"] = len(hashed)

    # ---------------------------------------------------------------- damage -> device (A2)
    dev = {}
    for kind, (zp, base) in {"T": (data2, "Transformer_Clip"), "F": (data1, "Fuse_Bank_Clip"),
                             "R": (data2, "Recloser_Bank_Clip")}.items():
        cols = read_dbf_columns(zp, base + ".dbf", ["circuit_id", "location_n"])
        pts = read_shp_points(zp, base + ".shp")
        by = defaultdict(lambda: ([], []))
        for c, loc, p in zip(cols["circuit_id"], cols["location_n"], pts):
            if down.get(loc, 0) > 0 and c.isdigit() and np.isfinite(p).all():
                by[f"{int(c):07d}"][0].append(loc)
                by[f"{int(c):07d}"][1].append(p)
        dev[kind] = {c: (locs, _to_m(np.array(ps)[:, 0], np.array(ps)[:, 1])) for c, (locs, ps) in by.items()}
    rule = {"Transformer": "T", "secondary": "T", "Fuse Bank": "F", "Recloser Bank": "R"}

    dmg = conn.execute("""SELECT rowid, circuit_id, asset_type, report_time, access_issue,
                                 special_equipment, lat, lon FROM damage_events ORDER BY rowid""").fetchall()
    rng = np.random.default_rng(REPLAY_SEED)
    updates = []
    mapped = 0
    for rowid, c, asset, rep, acc, spec, dlat, dlon in dmg:
        rep = str(rep or "")[:8]
        storm = _storm(rep)
        report_t = None
        if storm == "feb2025":
            day = date(int(rep[:4]), int(rep[4:6]), int(rep[6:8]))
            report_t = round((day - STORM_T0).days * 24 + float(rng.uniform(0, 24)), 2)  # A1 seeded hour
        base_h = job_base_hours(asset, str(acc).strip().lower() == "yes", spec)
        p = _to_m(dlon, dlat)
        kind = rule.get(asset, "T")
        best = None
        for kk in ([kind, "T"] if kind != "T" else ["T"]):
            if c in dev[kk]:
                locs, pts = dev[kk][c]
                d = np.hypot(*(pts - p).T)
                j = int(np.argmin(d))
                best = (kk, locs[j], float(d[j]))
                break
        loc = None
        if asset in NO_OUTAGE_ASSETS:
            best = None                         # capacitor/light damage doesn't drop customers
        if best is not None and best[2] <= MAX_MAP_M:
            kk, near, _ = best
            loc = near if (asset in ("Transformer", "secondary") or kk in "FR") else first_iso.get(near)
        if loc is None:
            updates.append((storm, None, report_t, base_h, None, 0, rowid))
            continue
        mapped += 1
        homes = int(down.get(loc, 0))
        priority = depth.get(loc, 99) - homes / 1e6          # A4: nearest the substation, then most homes
        updates.append((storm, hashed.get(loc) or hasher.hash_device(loc), report_t, base_h,
                        round(priority, 6), homes, rowid))
    conn.executemany("""UPDATE damage_events SET storm=?, device_key=?, report_t=?, base_hours=?,
                        priority=?, homes_affected=? WHERE rowid=?""", updates)
    stats["damage_rows"] = len(dmg)
    stats["damage_mapped"] = mapped

    # ---------------------------------------------------------------- circuits
    past = Counter(c for _, c, _, rep, *_ in dmg if str(rep or "")[:8] < HISTORY_CUTOFF)
    oh_by: dict = defaultdict(lambda: [0, 0])
    for c, o in zip(circ.tolist(), overhead):
        if o is not None:
            oh_by[c][0] += o
            oh_by[c][1] += 1
    for (c,) in conn.execute("SELECT circuit_id FROM circuits").fetchall():
        a, b = oh_by.get(c, (0, 0))
        conn.execute("UPDATE circuits SET past_damage = ?, pct_overhead = ? WHERE circuit_id = ?",
                     (past.get(c, 0), round(a / b, 4) if b else None, c))
    conn.commit()
    return stats

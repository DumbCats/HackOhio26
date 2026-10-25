"""Lane B risk model: feature + label building (read-only use of the DB and raw data).

Everything here is offline / warm-up work. Output arrays are aligned to the DB's
premises table sorted by premise_key. Raw ids and coordinates never leave this module
except into the gitignored data/model_cache/.

Label (A2 mapping, DATA_FACTS §4, prototype build.py):
    damage row -> nearest same-circuit device (Transformer / Fuse / Recloser layer,
    only devices that appear in some upstream chain) -> device key (LOC)
    -> every home whose upstream chain contains that key is "hit" in that storm.
    Transformer/secondary damage -> that transformer. Fuse/Recloser damage -> that
    device. Everything else (primary, Pole, Switch, ...) -> nearest transformer's
    first isolating device (or the breaker if none).
"""
from __future__ import annotations

import struct
import zipfile
from collections import Counter, defaultdict

import numpy as np

from app.models.common import CACHE_DIR, REPO_ROOT, damage_history, get_conn

RAW = REPO_ROOT / "aep-challenge" / "data" / "raw"
D1, D2, MU = RAW / "Data1.zip", RAW / "Data2.zip", RAW / "matched_upstream.zip"

# History cutoffs: damage strictly before the target storm's report window.
TARGETS = {
    "sep2024": "2024-09-26",   # train target; history = damage before Helene window
    "feb2025": "2025-02-12",   # test / served target; history = damage before Feb window
}
MAX_MAP_M = 1000.0           # damage farther than this from any same-circuit device is unmapped
NEAR_DMG_M = 1000.0          # "past damage near your home" radius
POLE_M = 300.0               # pole neighbourhood radius
M_PER_DEG_LAT = 111_000.0
M_PER_DEG_LON = 88_500.0     # cos(37.2 deg) * 111.3 km
WOOD = {"Pine", "Wood", "Cedar", "Ponderosa Pine", "Douglas Fir"}

# Model features, in order. history=True ones depend on the target's cutoff date.
FEATURES = [
    # name,             history
    ("overhead",        False),
    ("path_len",        False),
    ("section_size",    False),
    ("circ_oh_share",   False),
    ("circ_size",       False),
    ("pole_density",    False),
    ("pole_wood_share", False),
    ("pole_age",        False),
    ("circ_dmg_per1k",  True),
    ("near_dmg",        True),
    ("path_prior_hits", True),
]
FEATURE_NAMES = [f for f, _ in FEATURES]
HISTORY_FEATURES = [f for f, h in FEATURES if h]


# ---------------------------------------------------------------- raw readers ---
def read_dbf_columns(zip_path, member: str, want: list[str]) -> dict[str, np.ndarray]:
    """Fast column read of a .dbf inside a zip: returns {field: array of str}."""
    with zipfile.ZipFile(zip_path) as z:
        data = z.read(member)
    n, hl, rl = struct.unpack("<IHH", data[4:12])
    fields, off, pos = {}, 1, 32
    while data[pos] != 0x0D:
        name = data[pos:pos + 11].split(b"\0")[0].decode("ascii")
        length = data[pos + 16]
        fields[name] = (off, length)
        off += length
        pos += 32
    recs = np.frombuffer(data, dtype=f"S{rl}", count=n, offset=hl)
    raw = recs.view(np.uint8).reshape(n, rl)
    out = {}
    for f in want:
        o, ln = fields[f]
        col = np.ascontiguousarray(raw[:, o:o + ln]).view(f"S{ln}").ravel()
        out[f] = np.char.strip(np.char.decode(col, "latin1"))
    return out


def read_shp_points(zip_path, member: str) -> np.ndarray:
    """(n, 2) lon/lat for a point shapefile (types 1/11/21) inside a zip. NaN for null."""
    with zipfile.ZipFile(zip_path) as z:
        data = z.read(member)
    pts, pos, L = [], 100, len(data)
    while pos + 8 <= L:
        _, cl = struct.unpack_from(">2i", data, pos)
        t = struct.unpack_from("<i", data, pos + 8)[0]
        pts.append(struct.unpack_from("<2d", data, pos + 12) if t in (1, 11, 21) else (np.nan, np.nan))
        pos += 8 + cl * 2
    return np.asarray(pts, dtype=np.float64)


def to_m(lon, lat):
    return np.stack([np.asarray(lon) * M_PER_DEG_LON, np.asarray(lat) * M_PER_DEG_LAT], axis=-1)


def radius_sums(q: np.ndarray, p: np.ndarray, r: float, vals: list[np.ndarray]) -> tuple[np.ndarray, list]:
    """For each query point, count points within r and sum each value array over them.
    Grid-bucket index (cell = r) so 117k x 107k stays fast."""
    nq = len(q)
    cnt = np.zeros(nq)
    sums = [np.zeros(nq) for _ in vals]
    ok = np.isfinite(p).all(1)
    p = p[ok]
    vals = [v[ok] for v in vals]
    pc = np.floor(p / r).astype(np.int64)
    qc = np.floor(q / r).astype(np.int64)
    key = lambda c: c[:, 0] * 1_000_003 + c[:, 1]
    order = np.argsort(key(pc), kind="stable")
    pk = key(pc)[order]
    p, vals = p[order], [v[order] for v in vals]
    qk = key(qc)
    uq, inv = np.unique(qk, return_inverse=True)
    groups = defaultdict(list)
    for i, g in enumerate(inv):
        groups[g].append(i)
    for g, idx in groups.items():
        idx = np.asarray(idx)
        cx, cy = qc[idx[0]]
        cand = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                k = (cx + dx) * 1_000_003 + (cy + dy)
                a, b = np.searchsorted(pk, k), np.searchsorted(pk, k, side="right")
                if b > a:
                    cand.append(np.arange(a, b))
        if not cand:
            continue
        cand = np.concatenate(cand)
        d2 = ((q[idx, None, :] - p[None, cand, :]) ** 2).sum(-1)
        m = d2 <= r * r
        cnt[idx] = m.sum(1)
        for s, v in zip(sums, vals):
            s[idx] = m @ v[cand]
    return cnt, sums


# ---------------------------------------------------------------- build ---------
def _homes_from_db():
    conn = get_conn()
    rows = conn.execute(
        "SELECT premise_key, circuit_id, transformer_id, lat, lon FROM premises ORDER BY premise_key"
    ).fetchall()
    conn.close()
    keys = np.array([r[0] for r in rows])
    circ = np.array([r[1] for r in rows])
    lat = np.array([r[3] for r in rows], dtype=float)
    lon = np.array([r[4] for r in rows], dtype=float)
    return keys, circ, lat, lon


def build_all(verbose: bool = True) -> dict:
    """Build per-home static features, chains, damage mapping, labels and history
    features for every target. Returns a dict of numpy arrays (aligned to DB order)."""
    from ingest.hasher import PremiseHasher

    log = print if verbose else (lambda *a, **k: None)
    hasher = PremiseHasher(salt_path=str(REPO_ROOT / ".salt"))
    keys, circ, lat, lon = _homes_from_db()
    n = len(keys)
    idx_of = {k: i for i, k in enumerate(keys)}
    xy = to_m(lon, lat)
    log(f"homes in DB: {n}")

    # --- customers: overhead flag
    cu = read_dbf_columns(D1, "Customer_Clip.dbf", ["premise_nu", "kind_of_se"])
    kind = np.full(n, "", dtype=object)
    matched = 0
    for pn, ks in zip(cu["premise_nu"], cu["kind_of_se"]):
        i = idx_of.get(hasher.hash_premise(pn))
        if i is not None:
            kind[i] = ks
            matched += 1
    log(f"customer rows matched to DB keys: {matched}")
    overhead = np.where(kind == "Overhead", 1.0, np.where(kind == "Underground", 0.0, np.nan))

    # --- chains (matched_upstream): per home list of device keys (LOC), breaker last
    with zipfile.ZipFile(MU) as z:
        text = z.read("matched_upstream.txt").decode("latin1")
    chains: list[list[str] | None] = [None] * n
    down = Counter()
    first_iso = {}
    for line in text.splitlines():
        t = line.split("\t")
        if len(t) < 3:
            continue
        i = idx_of.get(hasher.hash_premise(t[0]))
        toks = [x.split("*") for x in t[1:]]
        if any(len(y) < 4 for y in toks):
            continue
        cb = "CB:" + toks[-1][3]
        ks = [y[3] for y in toks[:-1]] + [cb]
        iso = [y[3] for y in toks[1:-1] if y[0] == "eo_isolating_eqpt_inst"]
        first_iso[toks[0][3]] = iso[0] if iso else cb
        for k in ks:
            down[k] += 1
        if i is not None:
            chains[i] = ks
    del text
    has_topo = np.array([c is not None for c in chains])
    log(f"homes with an upstream chain: {has_topo.sum()}")

    path_len = np.array([len(c) if c else np.nan for c in chains], dtype=float)
    # homes behind the same first protective device (exposure of the home's section)
    section = np.full(n, np.nan)
    for i, c in enumerate(chains):
        if c:
            section[i] = down.get(first_iso.get(c[0], c[-1]), np.nan)

    # --- circuit-level static
    uc, cinv = np.unique(circ, return_inverse=True)
    c_homes = np.bincount(cinv).astype(float)
    oh_ok = np.isfinite(overhead)
    c_oh = np.bincount(cinv, weights=np.where(oh_ok, overhead, 0)) / np.maximum(np.bincount(cinv, weights=oh_ok.astype(float)), 1)
    overhead_f = np.where(oh_ok, overhead, c_oh[cinv])  # unknown service type -> circuit share

    # --- poles near the home
    po = read_dbf_columns(D1, "Pole_Clip.dbf", ["material", "date_insta", "date_manuf"])
    ppts = read_shp_points(D1, "Pole_Clip.shp")
    yr = np.zeros(len(ppts))
    for j, (a, b) in enumerate(zip(po["date_insta"], po["date_manuf"])):
        for s in (a, b):
            if len(s) >= 4 and s[:4].isdigit() and 1930 <= int(s[:4]) <= 2026:
                yr[j] = int(s[:4])
                break
    has_yr = (yr > 0).astype(float)
    wood = np.isin(po["material"], list(WOOD)).astype(float)
    pcnt, (pwood, pyr, pyrn) = radius_sums(xy, to_m(ppts[:, 0], ppts[:, 1]), POLE_M, [wood, yr, has_yr])
    pole_wood = np.where(pcnt > 0, pwood / np.maximum(pcnt, 1), np.nan)
    mean_yr = np.where(pyrn > 0, pyr / np.maximum(pyrn, 1), np.nan)
    pole_age = 2025.0 - mean_yr
    log(f"poles: {len(ppts)}; homes with >=1 pole within {POLE_M:.0f} m: {(pcnt > 0).sum()}")

    # --- damage -> device key (A2)
    dev = {}
    for k, (zp, base) in {"T": (D2, "Transformer_Clip"), "F": (D1, "Fuse_Bank_Clip"), "R": (D2, "Recloser_Bank_Clip")}.items():
        cols = read_dbf_columns(zp, base + ".dbf", ["circuit_id", "location_n"])
        pts = read_shp_points(zp, base + ".shp")
        by = defaultdict(lambda: ([], []))
        for c, loc, p in zip(cols["circuit_id"], cols["location_n"], pts):
            if down.get(loc, 0) > 0 and c.isdigit() and np.isfinite(p).all():
                by[f"{int(c):07d}"][0].append(loc)
                by[f"{int(c):07d}"][1].append(p)
        dev[k] = {c: (locs, to_m(np.array(ps)[:, 0], np.array(ps)[:, 1])) for c, (locs, ps) in by.items()}
    rule = {"Transformer": "T", "secondary": "T", "Fuse Bank": "F", "Recloser Bank": "R"}

    dmg = damage_history()
    d_key, d_dist = [], []
    for r in dmg:
        c = r["circuit_id"]
        p = to_m(r["lon"], r["lat"])
        k = rule.get(r["asset_type"], "T")
        best = None
        for kk in ([k, "T"] if k != "T" else ["T"]):
            if c in dev[kk]:
                locs, pts = dev[kk][c]
                d = np.hypot(*(pts - p).T)
                j = int(np.argmin(d))
                best = (kk, locs[j], float(d[j]))
                break
        if best is None or best[2] > MAX_MAP_M:
            d_key.append(None)
            d_dist.append(np.nan if best is None else best[2])
            continue
        kk, loc, dist = best
        key = loc if (r["asset_type"] in ("Transformer", "secondary") or kk in "FR") else first_iso.get(loc)
        d_key.append(key)
        d_dist.append(dist)
    log(f"damage rows: {len(dmg)}; mapped to a device: {sum(k is not None for k in d_key)}")

    # flat chain index for fast "does chain contain a hit key"
    vocab = {}
    flat, offs = [], []
    for c in chains:
        offs.append(len(flat))
        for k in (c or []):
            flat.append(vocab.setdefault(k, len(vocab)))
    flat = np.asarray(flat, dtype=np.int64)
    offs = np.asarray(offs + [len(flat)], dtype=np.int64)
    seg_len = np.diff(offs)
    seg_id = np.repeat(np.arange(n), seg_len)

    def per_home_hits(rows_mask: np.ndarray) -> np.ndarray:
        """number of selected damage rows whose device key is on each home's chain."""
        kc = Counter(k for k, m in zip(d_key, rows_mask) if m and k is not None)
        w = np.zeros(len(vocab) + 1)
        for k, v in kc.items():
            if k in vocab:
                w[vocab[k]] = v
        return np.bincount(seg_id, weights=w[flat], minlength=n)

    storm = np.array([r["storm"] for r in dmg])
    rep = np.array([r["report_date"] for r in dmg])
    dcirc = np.array([r["circuit_id"] for r in dmg])
    dxy = to_m(np.array([r["lon"] for r in dmg]), np.array([r["lat"] for r in dmg]))

    out = dict(
        keys=keys, circ_index=cinv, has_topo=has_topo,
        overhead=overhead_f,
        path_len=np.log1p(path_len),
        section_size=np.log1p(section),
        circ_oh_share=c_oh[cinv],
        circ_size=np.log(c_homes[cinv]),
        pole_density=np.log1p(pcnt),
        pole_wood_share=pole_wood,
        pole_age=pole_age,
    )
    circ_pos = {c: j for j, c in enumerate(uc)}
    for tgt, cutoff in TARGETS.items():
        hist = (rep < cutoff) & (storm != tgt)
        c_cnt = np.zeros(len(uc))
        for c in dcirc[hist]:
            if c in circ_pos:
                c_cnt[circ_pos[c]] += 1
        out[f"label_{tgt}"] = (per_home_hits(storm == tgt) > 0).astype(np.int8)
        out[f"circ_rows_{tgt}"] = c_cnt[cinv]
        out[f"circ_dmg_per1k_{tgt}"] = np.log1p(1000.0 * c_cnt[cinv] / c_homes[cinv])
        near, _ = radius_sums(xy, dxy[hist], NEAR_DMG_M, [])
        out[f"near_dmg_{tgt}"] = np.log1p(near)
        out[f"path_prior_hits_{tgt}"] = np.log1p(per_home_hits(hist))
        out[f"baseline_{tgt}"] = 1000.0 * c_cnt[cinv] / c_homes[cinv]   # A5 heuristic (prototype final.py)
        log(f"{tgt}: history rows {hist.sum()}, hit homes {out[f'label_{tgt}'].sum()} "
            f"({out[f'label_{tgt}'][has_topo].mean():.1%} of homes with topology)")
    out["map_stats"] = np.array([len(dmg), sum(k is not None for k in d_key)])
    return out


FEATURES_CACHE = CACHE_DIR / "risk_features.npz"


def ensure_cache_dir():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    gi = CACHE_DIR / ".gitignore"
    if not gi.exists():
        gi.write_text("*\n")


def load_features(rebuild: bool = False, verbose: bool = False) -> dict:
    """Features from the gitignored cache, building it from DB + raw on first use."""
    ensure_cache_dir()
    if FEATURES_CACHE.exists() and not rebuild:
        with np.load(FEATURES_CACHE, allow_pickle=False) as z:
            return {k: z[k] for k in z.files}
    out = build_all(verbose=verbose)
    np.savez_compressed(FEATURES_CACHE, **out)
    return out


def design_matrix(feat: dict, target: str) -> np.ndarray:
    """(n, F) raw feature matrix for a target (history features use that target's cutoff)."""
    cols = []
    for name, hist in FEATURES:
        cols.append(feat[f"{name}_{target}"] if hist else feat[name])
    return np.stack(cols, axis=1).astype(np.float64)

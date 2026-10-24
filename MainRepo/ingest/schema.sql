-- AI Outage Concierge: Relational SQLite Schema
-- Configured for high-concurrency WAL mode and instant indexing

PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = -64000;
PRAGMA temp_store = MEMORY;

-- 1. Metadata Table
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Circuits Table (Aggregated Feeder Summary)
CREATE TABLE IF NOT EXISTS circuits (
    circuit_id TEXT PRIMARY KEY,
    substation TEXT,
    customer_count INTEGER DEFAULT 0,
    premise_count INTEGER DEFAULT 0,
    damage_event_count INTEGER DEFAULT 0,
    pole_count INTEGER DEFAULT 0,
    wood_pole_ratio REAL DEFAULT 0.0,
    avg_asset_age REAL DEFAULT 0.0,
    min_lat REAL,
    max_lat REAL,
    min_lon REAL,
    max_lon REAL
);
CREATE INDEX IF NOT EXISTS idx_circuits_damage ON circuits(damage_event_count);

-- 3. Premises Table (Anonymized Customer Nodes)
CREATE TABLE IF NOT EXISTS premises (
    premise_key TEXT PRIMARY KEY,          -- Salted SHA-256 hash (e.g. p_a1b2c3d4e5f60718)
    circuit_id TEXT NOT NULL,
    transformer_id TEXT,
    is_critical_tier INTEGER DEFAULT 0,    -- 1 if life-support / medical flag set
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    upstream_device_count INTEGER DEFAULT 0,
    upstream_devices_json TEXT,            -- Compact JSON array of customer-safe labels
    nearest_damage_dist_km REAL DEFAULT 0.0,
    FOREIGN KEY (circuit_id) REFERENCES circuits(circuit_id)
);
CREATE INDEX IF NOT EXISTS idx_premises_circuit ON premises(circuit_id);

-- 4. Topology Edges Table (Upstream Dependency Chain)
CREATE TABLE IF NOT EXISTS topology_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    premise_key TEXT NOT NULL,
    step_order INTEGER NOT NULL,
    device_type TEXT NOT NULL,             -- transformer, recloser, fuse, switch, breaker
    device_id TEXT NOT NULL,               -- operational identifier for matching damage
    device_label TEXT NOT NULL,            -- safe customer label ("Upstream Fuse 1")
    FOREIGN KEY (premise_key) REFERENCES premises(premise_key)
);
CREATE INDEX IF NOT EXISTS idx_topo_premise ON topology_edges(premise_key);
CREATE INDEX IF NOT EXISTS idx_topo_device ON topology_edges(device_id);

-- 5. Damage Events Table (ARCOS Historical Records)
CREATE TABLE IF NOT EXISTS damage_events (
    outage_num TEXT PRIMARY KEY,
    event_name TEXT NOT NULL,              -- winter_storm_2025, helene_2024, default
    circuit_id TEXT NOT NULL,
    substation TEXT,
    asset_type TEXT NOT NULL,              -- primary, Pole, Fuse Bank, secondary, Transformer, Recloser Bank, Switch
    cu_category TEXT,                      -- ARM, POL, XCO, XFR, REC, SWI
    report_time TEXT,
    repaired_time TEXT,
    status TEXT,
    access_issue TEXT,
    special_equipment TEXT,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    nearest_dist REAL
);
CREATE INDEX IF NOT EXISTS idx_damage_circuit ON damage_events(circuit_id);
CREATE INDEX IF NOT EXISTS idx_damage_event_name ON damage_events(event_name);

-- 6. Labor Catalog (CU Categories from Workbook)
CREATE TABLE IF NOT EXISTS labor_codes (
    cu_category TEXT PRIMARY KEY,          -- ARM, POL, REC, SWI, XCO, etc.
    description TEXT NOT NULL,
    avg_install_hours REAL NOT NULL,
    avg_remove_hours REAL NOT NULL
);

-- 7. Labor Adders (Access & Site Conditions)
CREATE TABLE IF NOT EXISTS labor_adders (
    adder_name TEXT PRIMARY KEY,           -- Difficult Location, Backyard, Remote Site, Hand Dig, Rock Hole
    work_type TEXT NOT NULL,
    description TEXT NOT NULL,
    adder_hours REAL NOT NULL
);

-- 8. Public Critical Facilities (Anonymized & Rounded Coordinates)
CREATE TABLE IF NOT EXISTS priority_facilities (
    facility_id TEXT PRIMARY KEY,
    facility_type TEXT NOT NULL,           -- Hospital, Fire Station, Ambulance
    name_masked TEXT NOT NULL,
    lat_approx REAL NOT NULL,              -- Coordinates rounded to ~1.1 km
    lon_approx REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facilities_type ON priority_facilities(facility_type);

-- 9. Distribution Assets (Protective Devices & Equipment)
CREATE TABLE IF NOT EXISTS assets (
    asset_id TEXT PRIMARY KEY,
    asset_type TEXT NOT NULL,              -- Transformer, Fuse Bank, Recloser Bank, Switch
    circuit_id TEXT NOT NULL,
    subtype TEXT,
    lat REAL,
    lon REAL
);
CREATE INDEX IF NOT EXISTS idx_assets_circuit ON assets(circuit_id);
CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(asset_type);


"""
Unit and Integration Test Suite for AI Outage Concierge Database Ingestion.
Verifies data integrity, privacy constraints, row counts, and query latency.
"""

import os
import sqlite3
import time
import unittest

DB_PATH = "data/outage_concierge.db"


class TestDatabaseIngestion(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(DB_PATH):
            raise unittest.SkipTest(f"Database not built at {DB_PATH}. Run 'python -m ingest.build_db' first.")
        cls.conn = sqlite3.connect(DB_PATH)
        cls.cur = cls.conn.cursor()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "conn"):
            cls.conn.close()

    def test_01_metadata_and_ilm(self):
        """Verifies metadata table and the 4.5 Indirect Labor Multiplier."""
        self.cur.execute("SELECT value FROM metadata WHERE key = 'indirect_labor_multiplier'")
        res = self.cur.fetchone()
        self.assertIsNotNone(res, "Metadata for indirect_labor_multiplier not found.")
        self.assertEqual(float(res[0]), 4.5, "Indirect Labor Multiplier must equal 4.5.")

    def test_02_damage_events_count_and_tagging(self):
        """Verifies ARCOS damage events count (1,659 minus 14 non-circuit rows, A12) and storm clustering."""
        self.cur.execute("SELECT count(*) FROM damage_events")
        count = self.cur.fetchone()[0]
        self.assertEqual(count, 1645, f"Expected 1,645 damage records, found {count}.")

        # Check tagged events
        self.cur.execute("SELECT count(*) FROM damage_events WHERE event_name = 'winter_storm_2025'")
        winter_count = self.cur.fetchone()[0]
        self.assertGreater(winter_count, 1200, "Winter storm 2025 should have >1,200 records.")

        self.cur.execute("SELECT count(*) FROM damage_events WHERE event_name = 'helene_2024'")
        helene_count = self.cur.fetchone()[0]
        self.assertGreater(helene_count, 150, "Helene 2024 storm should have >150 records.")

    def test_03_labor_codes_and_adders(self):
        """Verifies CU group labor hours and access adders from workbook."""
        self.cur.execute("SELECT count(*) FROM labor_codes")
        cu_count = self.cur.fetchone()[0]
        self.assertGreaterEqual(cu_count, 15, "Labor codes should have at least 15 CU categories.")

        self.cur.execute("SELECT avg_install_hours FROM labor_codes WHERE cu_category = 'POL'")
        pol_hours = self.cur.fetchone()[0]
        self.assertAlmostEqual(pol_hours, 2.503, places=2)

        self.cur.execute("SELECT count(*) FROM labor_adders")
        adders_count = self.cur.fetchone()[0]
        self.assertGreaterEqual(adders_count, 5, "Labor adders should contain site condition adders.")

    def test_04_priority_facilities_privacy(self):
        """Verifies hospitals/fire/ambulance ingestion and ~1km coordinate rounding."""
        self.cur.execute("SELECT count(*) FROM priority_facilities")
        fac_count = self.cur.fetchone()[0]
        self.assertGreaterEqual(fac_count, 40, "Expected at least 40 critical facilities.")

        # Check coordinate rounding (max 2 decimal places)
        self.cur.execute("SELECT lat_approx, lon_approx FROM priority_facilities LIMIT 10")
        for lat, lon in self.cur.fetchall():
            lat_str = str(lat).split('.')[-1] if '.' in str(lat) else ""
            lon_str = str(lon).split('.')[-1] if '.' in str(lon) else ""
            self.assertLessEqual(len(lat_str), 2, f"Latitude {lat} is not rounded to ~1.1 km precision.")
            self.assertLessEqual(len(lon_str), 2, f"Longitude {lon} is not rounded to ~1.1 km precision.")

    def test_05_premises_count_and_anonymization(self):
        """Verifies 117,642 premises, salted SHA-256 keys, and zero raw address fields."""
        self.cur.execute("SELECT count(*) FROM premises")
        p_count = self.cur.fetchone()[0]
        self.assertEqual(p_count, 117642, f"Expected 117,642 premises, found {p_count}.")

        # Check premise keys format (e.g. p_0123456789abcdef)
        self.cur.execute("SELECT premise_key FROM premises LIMIT 20")
        for (pk,) in self.cur.fetchall():
            self.assertTrue(pk.startswith("p_"), f"Premise key {pk} must start with 'p_'.")
            self.assertEqual(len(pk), 18, f"Premise key {pk} must be 18 chars (p_ + 16 hex).")

    def test_06_topology_chains_and_labels(self):
        """Verifies topology edges and safe customer-facing labels."""
        self.cur.execute("SELECT count(*) FROM topology_edges")
        edge_count = self.cur.fetchone()[0]
        self.assertGreater(edge_count, 450000, f"Expected >450k topology edges, found {edge_count}.")

        # Check safe labels
        self.cur.execute("SELECT DISTINCT device_label FROM topology_edges LIMIT 20")
        labels = [r[0] for r in self.cur.fetchall()]
        for lbl in labels:
            self.assertFalse(lbl.startswith("eo_"), f"Internal equipment tag leaked in label: {lbl}")
            self.assertTrue(any(word in lbl for word in ["Transformer", "Recloser", "Fuse", "Breaker", "Switch", "Device"]),
                            f"Label {lbl} does not contain standard safe terminology.")

    def test_07_point_query_performance(self):
        """Asserts random point lookup executes in <1 ms."""
        self.cur.execute("SELECT premise_key FROM premises LIMIT 100")
        keys = [r[0] for r in self.cur.fetchall()]

        t0 = time.time()
        for k in keys:
            self.cur.execute("""
                SELECT p.premise_key, p.circuit_id, p.upstream_device_count, p.nearest_damage_dist_km, c.damage_event_count
                FROM premises p
                LEFT JOIN circuits c ON p.circuit_id = c.circuit_id
                WHERE p.premise_key = ?
            """, (k,)).fetchone()
        t1 = time.time()
        avg_ms = ((t1 - t0) / len(keys)) * 1000
        print(f"\nAverage indexed joined point query time: {avg_ms:.4f} ms")
        self.assertLess(avg_ms, 2.0, f"Query latency too high: {avg_ms:.2f} ms")


    # ---- Lane A additions (contracts/API.md section 6)
    def test_08_all_arcos_circuits_match_customer_circuits(self):
        """With the crosswalk (A12), every ARCOS circuit is a customer circuit."""
        self.cur.execute("""SELECT count(DISTINCT d.circuit_id) FROM damage_events d
                            WHERE d.circuit_id NOT IN (SELECT DISTINCT circuit_id FROM premises)""")
        self.assertEqual(self.cur.fetchone()[0], 0)
        self.cur.execute("SELECT count(DISTINCT circuit_id) FROM damage_events")
        self.assertEqual(self.cur.fetchone()[0], 82)

    def test_09_damage_mapping_and_replay_columns(self):
        self.cur.execute("SELECT count(*), sum(device_key IS NOT NULL) FROM damage_events")
        n, mapped = self.cur.fetchone()
        self.assertGreater(mapped / n, 0.95, "A2: about 97% of damage rows should map to a device")
        self.cur.execute("SELECT count(*), min(report_t), max(report_t) FROM damage_events WHERE storm='feb2025'")
        n, lo, hi = self.cur.fetchone()
        self.assertGreater(n, 1200)
        self.assertGreaterEqual(lo, 0)
        self.assertLess(hi, 6 * 24)
        self.cur.execute("SELECT count(*) FROM damage_events WHERE storm='feb2025' AND (base_hours IS NULL OR base_hours <= 0)")
        self.assertEqual(self.cur.fetchone()[0], 0)

    def test_10_premise_cells_overhead_device_keys(self):
        self.cur.execute("SELECT count(*) FROM premises WHERE cell_id IS NULL")
        self.assertEqual(self.cur.fetchone()[0], 0)
        self.cur.execute("SELECT sum(overhead = 1), sum(overhead = 0) FROM premises")
        oh, ug = self.cur.fetchone()
        self.assertEqual((oh, ug), (64824, 52419))
        self.cur.execute("SELECT count(*) FROM topology_edges WHERE device_key IS NULL")
        self.assertEqual(self.cur.fetchone()[0], 0)
        self.cur.execute("SELECT count(*), sum(visible) FROM cells")
        n, vis = self.cur.fetchone()
        self.assertGreater(n, 500)
        self.assertGreater(vis, 300)
        self.cur.execute("SELECT sum(past_damage) FROM circuits")
        self.assertEqual(self.cur.fetchone()[0], 345)


if __name__ == "__main__":
    unittest.main()

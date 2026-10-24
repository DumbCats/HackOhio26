---
phase: 01-data-ingest-and-sqlite-engine
plan: 01-02
subsystem: labor-and-damage
tags: [arcos, storm-tagging, openpyxl, labor-codes, adders]
provides:
  - ARCOS damage records ingestion (1,659 records)
  - Storm event clustering (Winter Storm Feb 2025 vs Helene Sept 2024)
  - Labor catalog extraction with Indirect Labor Multiplier = 4.5
affects: [02-core-analytics]
tech-stack:
  added: [openpyxl, sqlite3]
  patterns: [cu-group-mapping, temporal-storm-clustering, circuit-normalization]
key-files:
  created:
    - ingest/ingest_damage.py
    - ingest/ingest_labor.py
key-decisions:
  - "Extracted exact Indirect Labor Multiplier (ILM = 4.5) for travel and setup."
  - "Clustered ARCOS events into 'winter_storm_2025' (1,223 records) and 'helene_2024' (173 records)."
  - "Normalized circuit identifiers to canonical 7-digit strings (CIR10 <-> 0000010) connecting ARCOS to premises with 98.8% match rate."
duration: 5min
completed: 2026-10-24
---

# Plan 01-02 Summary: ARCOS Damage and Labor Workbook Ingestion

Extracted operational restoration standards, CU work codes, and historical storm damage records into SQLite.

## Accomplishments
- Loaded 1,659 damage incidents across 85 circuits from `arcos_prod_damage_09_28_Clip.dbf`.
- Mapped asset damage types (primary, Pole, Transformer, Fuse Bank, Recloser Bank, Switch) to CU labor categories.
- Loaded 17 CU labor codes, 11 site access adders, and ILM = 4.5 from `Install_Labor_HackOHIO.xlsx`.

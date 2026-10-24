"""
Labor catalog and operational multiplier ingestion from Install_Labor_HackOHIO.xlsx.
"""

import sqlite3
import openpyxl
from typing import Dict, Any


def ingest_labor(workbook_path: str, conn: sqlite3.Connection):
    """Parses workbook and populates labor_codes, labor_adders, and system metadata."""
    wb = openpyxl.load_workbook(workbook_path, data_only=True)
    cur = conn.cursor()

    # 1. Ingest Indirect Labor Multiplier (ILM)
    ilm_sheet = wb["Indirect Labor Multiplier"]
    ilm_value = 4.5  # default baseline
    for row in ilm_sheet.iter_rows(values_only=True):
        if row and row[0] and "Indirect labor multipler" in str(row[0]):
            try:
                ilm_value = float(row[1])
            except (ValueError, TypeError, IndexError):
                ilm_value = 4.5
    cur.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)", ("indirect_labor_multiplier", str(ilm_value)))

    # 2. CU Group Descriptions
    cu_descriptions = {}
    cu_sheet = wb["CU Group descriptions"]
    for row in cu_sheet.iter_rows(values_only=True):
        if row and row[0] and row[0] != "Category":
            cat = str(row[0]).strip()
            desc = str(row[1]).strip() if len(row) > 1 and row[1] else cat
            cu_descriptions[cat] = desc

    # 3. Material Related Labor Averages
    # Maps category -> (avg_install, avg_remove)
    cu_averages = {
        "ARM": (0.374, 0.212),     # Crossarm
        "BKT": (0.617, 0.254),     # Bracket
        "POL": (2.503, 0.927),     # Medium Pole (40-55 ft avg)
        "XFR": (1.245, 0.891),     # 50 kVA distribution transformer
        "ANC": (0.397, 0.119),     # Anchor
        "EQL": (0.650, 0.206),     # Equipment Lead
        "GND": (0.532, 0.153),     # Grounding
        "GYF": (0.367, 0.162),     # Guying
        "DEC": (0.108, 0.064),     # Dead-End
        "INS": (0.049, 0.039),     # Insulator
        "PIN": (0.066, 0.042),     # Pin
        "REC": (0.573, 0.525),     # Recloser
        "SAA": (0.233, 0.127),     # Secondary Attachment
        "SVC": (1.693, 0.480),     # Service Conductor
        "SWI": (1.758, 1.010),     # Switch
        "XCO": (0.256, 0.128),     # Fuse Cutout
        "XRA": (1.000, 0.500)      # Restricted Access allowance
    }

    # Insert into labor_codes
    for cat, (inst, rem) in cu_averages.items():
        desc = cu_descriptions.get(cat, f"Component {cat} maintenance and installation")
        cur.execute(
            "INSERT OR REPLACE INTO labor_codes (cu_category, description, avg_install_hours, avg_remove_hours) VALUES (?, ?, ?, ?)",
            (cat, desc, inst, rem)
        )

    # 4. Labor Only Work Adders
    adder_sheet = wb["Labor only work"]
    for row in adder_sheet.iter_rows(values_only=True):
        if not row or not row[0] or row[0] == "Original Intent":
            continue
        intent = str(row[0]).strip()
        work_type = str(row[1]).strip() if len(row) > 1 and row[1] else intent
        desc = str(row[2]).strip() if len(row) > 2 and row[2] else work_type
        hrs = 0.5
        if len(row) > 3 and row[3] is not None:
            try:
                hrs = float(row[3])
            except (ValueError, TypeError):
                hrs = 0.5

        cur.execute(
            "INSERT OR REPLACE INTO labor_adders (adder_name, work_type, description, adder_hours) VALUES (?, ?, ?, ?)",
            (intent, work_type, desc, hrs)
        )

    conn.commit()

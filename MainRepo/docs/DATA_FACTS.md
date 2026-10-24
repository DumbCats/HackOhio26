# Data facts (verified 2026-10-24)

Scripted recon of the raw AEP data. Field names and join rules are verified; items marked UNSURE are best guesses. Lane A builds from this.

All layers are **PointZ (shp type 11)** in **WGS84 lon/lat** (GEOGCS), except Primary/Secondary (PolylineZ, also WGS84) and the 3 facility layers (**Web Mercator EPSG:3857**, so they need conversion). Customers bbox: lon −80.252..−79.647, lat 36.995..37.480.

## 1. Customer_Clip (117,642 rows = premises)
Fields: id N, critical_c C, special_op C, aep_locati C, aep_xfmr_l C, road_id N, aep_string N, customer_c N, address C(all empty), road_name C, city C, state C, circuit_id C, kind_of_se C, address_nu C(empty), service_po F(=lon), service__1 F(=lat), street_cod C, macss_mete C(empty), anno_strin C, rotation F, esri_defau C, eo_source_ C, premise_nu C.
- **circuit_id**: 7-digit zero-padded ('0000060'), 110 distinct. **Transformer link: aep_xfmr_l** (= Transformer.location_n). **premise_nu** = matched_upstream line key.
- **OH/UG = kind_of_se**: Overhead 64,824 / Underground 52,419 / Unknown 399.
- **critical_c**: 'N/A' 117,529 / 'LS Life Support' 113. **special_op**: 100% empty. **esri_defau**: NORMAL 117,515 / THREAT 127.
- customer_c looks like customers per service location (1 = 103,621). UNSURE.

## 2. Circuit IDs. The numbering is NOT plain int-equal!
- ARCOS `Circuit`: 'CIRnn' (1,645 rows) plus non-circuit 'PENN FOREST' 7, 'TINKER' 6, 'SERVICE CENTER' 1, giving 85 distinct strings and 82 CIR circuits.
- Customer/Transformer/Fuse/Recloser/Switch `circuit_id` is 7 digits. Their `aep_circui` = 'CIRnn'. Primary circuit_id is always int-equal to its aep_circui.
- Device layers give a deterministic crosswalk, 7-digit → CIR: **2–11 → id+1; 13–15 → id+1; 16 → CIR2; all others identity** (12 is absent). Saved: `ingest/circuit_crosswalk.json`.
- With the crosswalk, **all 82 CIR circuits match customer circuits** (naive int match: 81, with 22–30% of device rows mis-assigned). There are 110 distinct customer circuits. Nearest-Primary circuit agrees with the ARCOS circuit 95%.

## 3. matched_upstream.txt (117,599 lines, CRLF, ~28 MB)
`<PREMISE>\t<tok>\t<tok>…`, where tok = `type*<ID9>*subtype*<LOC>` with `*` inside the token.
```
<PREMISE>\teo_power_xfrmr_inst*<ID>*Distribution*<LOC>\teo_isolating_eqpt_inst*<ID>*Fuse*<LOC>\teo_isolating_eqpt_inst*<ID>*Recloser (Hydraulic)*<LOC>\teo_circuit*<ID>*Circuit Breaker*<CIRCUIT7>
<PREMISE>\teo_power_xfrmr_inst*<ID>*Distribution*<LOC>\teo_isolating_eqpt_inst*<ID>*Recloser (Electronic)*<LOC>\teo_circuit*<ID>*Circuit Breaker*<CIRCUIT7>
```
Tokens per line: 3:6,987 · 4:30,184 · 5:43,746 · 6:21,713 · 7:8,316 · 8:3,263 · 9+:3,390 (max 14). Order runs from the transformer upstream to the breaker. Chains are consistent per transformer.

| element | match |
|---|---|
| head → Customer.premise_nu | 117,595/117,599 |
| Distribution xfmr ID → Transformer.id; LOC → location_n | 25,300 / 25,298 of 25,302 |
| Fuse ID → Fuse_Bank.id; LOC → location_n | 6,656/6,757; 6,453/6,511 |
| Recloser LOC → Recloser_Bank.location_n (id: 0%) | 321/321 |
| Circuit LOC = customer circuit_id (7-digit) | 110/110; per-customer 117,588 |
| Step xfmr (107), Sectionalizer (1), circuit ID9 | no layer match |
global_id/OBJECTID never match. Switches are not in chains. Transformer.upstream_l = next device LOC (93%).

## 4. Damage → device
- **NEAR_DIST = degrees** (max 0.000547 ≈ 50 m) to the **nearest Primary line** (1,659/1,659 recomputed). NEAR_FID matches exported Primary row+1 in only 627 rows (pre-export OBJECTID), so **do not use it**.
- Mapping: map CIR to customer circuit via the crosswalk. Then: Transformer/secondary → nearest Transformer on that circuit → its premises. Fuse Bank / Recloser Bank → nearest same-circuit fuse/recloser (matched on LOC in chains) → all premises whose chain contains it. primary/Pole/Switch/other → nearest same-circuit transformer → its first isolating device → downstream premises.
- Feasibility: 1,645/1,659 (99.2%) mapped. Device distance ≤100 m 80%, ≤250 m 93%, ≤1 km 97%. Fuse/Transformer/Recloser points are at P90 = 0 m. Median affected: primary 20, Pole 25, Fuse 11, Recloser 91, Transformer 3.
- **Feb 13–17 2025**: 1,223 rows (Feb 12: 25, Feb 18: 6), 62 CIR circuits plus 7 non-CIR rows, **85,719 customers** on those circuits (81 Life Support).

## 5. Pole_Clip (107,013): **no circuit field**
Fields: id, status, location_n, usage, number(empty), owner_name, date_insta D, date_ins_1 C, aep_moved_, material, aep_plant_(empty), height, class, treatment(empty), aep_ciac(empty), ciac_date(empty), date_manuf D, reinforcem, esri_defau, eo_source_, rotation, owner_type, global_id.
- date_insta: 49.8% null, 1800–2026 (84 <1930), P50 1999. date_manuf: 21.4% null, 1900–2026 (81 = 1900 sentinel), P50 1991. Taking coalesce gives 84,165 usable (78.6%).
- material: Pine 78,062, Wood 23,785, Fiberglass 3,543, Aluminium 644, Steel 520, Cedar 135, Ornamental 120, Concrete 114, Unknown 48, Ponderosa Pine 38, Douglas Fir 4.

## 6. Facilities (HIFLD schema)
Fields: PERMANENT_, SOURCE_*, LOADDATE, FTYPE, FCODE, NAME, ADDRESS, CITY, STATE, ZIPCODE, GNIS_ID… Hospitals 5 (FCODE 80012), Fire 37 (74026), Ambulance 10 (74001).

## 7. Labor xlsx: CNC (95 connectors), material averages, labor adders, ILM, CU groups
CU groups: ARM crossarm, BKT bracket, POL pole, ANC anchor, EQL equipment lead, GND ground, GYF guy, DEC dead-end, DEG formed retention, INS insulator, PIN pin, REC recloser, SAA secondary attachment, SVC service drop, SWI switch, XCO fuse cutout, XRA access adder. **ILM = 4.5×.** There is **no conductor/wire, capacitor or light CU**.

| Asset_Type (count) | Inform_Wor | hrs (inst+rem) | built from |
|---|---|---|---|
| primary (704) | Damaged Wire | 1.129 UNSURE | 2×DEC .172 + 2×CNC avg .260 + 3×INS .089 |
| Pole (355) | Damaged Pole | 4.812 | POL Medium 3.430 + ARM .586 + GYF .529 + 3×INS |
| Fuse Bank (280) | Damaged Switch | 1.240 | XCO .384 + EQL .856 |
| secondary (156) | Damaged Wire | 0.879 UNSURE | SAA .359 + 2×CNC |
| Transformer (74) | Damaged Equip | 3.234 | 25 kVA 1.994 (UNSURE size) + XCO + EQL |
| Recloser Bank (58) | Damaged Switch | 1.954 | REC 1.098 + EQL |
| Switch (19) | Damaged Switch | 2.768 | SWI |
| Capacitor Bank (6) | Damaged Equip | 2.008 UNSURE | EQL + 3×XCO |
| Light (5) | Damaged Light | 0.872 UNSURE | BKT |
| Step Transformer (1) | Damaged Equip | 3.200 UNSURE | 833 kVA 2.344 + EQL |
| '' (1) | Damaged Wire | treat as primary | |
Adders: Access_Iss=Yes +0.5; Special_Eq Backyard Bucket +0.5; Track Hoe/Yard Dog +1.312. Multiply the total by 4.5.

## 8. ARCOS repair days (dates only, no times)
| set | n | P10 | P50 | P90 | mean | max |
|---|---|---|---|---|---|---|
| all Repaired=Yes | 1,583 | 0 | 1 | 23 | 8.02 | 221 |
| excl. Repaired_D 2024-10-22 batch | 1,445 | 0 | 1 | 5 | 5.91 | 221 |
| Feb 13–17 2025 | 1,181 | 0 | 1 | 2 | 1.31 | 137 |
- The **Oct-22-2024 batch is in Repaired_D** (138 rows, reported Sep 27–Oct 2 2024 plus Aug). No Report_Tim falls on that date. It is a bulk close-out, so exclude it.
- **Repaired=No (76)**: placeholder Repaired_D 2025-12-29 ×35, 2025-10-24 ×24, other late-2025/2026 dates. 42 of these rows are in the Feb storm.

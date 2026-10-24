# Risk model card (Lane B)

**What it does:** puts each home in a **High / Medium / Low** band for losing power in the
winter storm, *compared with other homes in the area*. It never gives a percent chance.

Rebuild everything: `.venv/bin/python -m app.models.train_risk` (about 3 seconds). Only the
per-home score cache: `... -m app.models.train_risk --score`. Weights and metrics are in
`app/models/artifacts/risk_model.json`. Per-home data stays in `data/model_cache/`, which git ignores.

## What "hit" means (the label)
A home is **hit** in a storm if that storm's damage landed on equipment that feeds the home.
We use the A2 mapping (DATA_FACTS §4): each damage record goes to the nearest device of the
matching type (transformer, fuse, or recloser) on the same circuit, after fixing the circuit
ids (A12). Damage to a line, pole, or switch goes to the nearest transformer's first fuse or
recloser. Then every home whose upstream chain (`matched_upstream.txt`) includes that device
is hit. Records more than 1 km from any device on their circuit are skipped.
1,596 of 1,645 damage records get mapped.
- Sep 2024 storm (Helene, Sep 26 to Oct 2): **5,195 homes hit (4.4%)**
- Feb 2025 storm (Feb 12 to 18): **26,163 homes hit (22.2%)**

## Features (only things known before the storm)
| feature | what it is |
|---|---|
| circ_dmg_per1k | past damage records on the home's circuit per 1,000 homes, log scale (the A5 history term) |
| near_dmg | past damage records within 1 km of the home, log scale |
| path_prior_hits | past damage records on the home's own upstream equipment, log scale |
| overhead | service drop is overhead (Customer `kind_of_se`; unknown uses the circuit's overhead share) |
| path_len | number of devices between the home and the breaker, log scale |
| section_size | homes behind the same first fuse or recloser as this home, log scale |
| circ_oh_share, circ_size | circuit's overhead share, log of the circuit's home count |
| pole_density, pole_wood_share, pole_age | poles within 300 m: count (log), share that are wood, mean age (install or manufacture year) |

"Past" means records dated before the target storm's window: before 2024-09-26 for Sep
(89 records), before 2025-02-12 for Feb (345 records). Rows from Feb 12 count as part of the
storm, not as history. `is_critical_tier` is never used. History features are standardized
within each scoring set, because the two history windows are very different in length.

## Model and validation (time-split, no peeking at the future)
- **Learned part:** L2 logistic regression in numpy (Newton's method, deterministic), trained
  **only on the Sep 2024 storm**. Signs are fixed in advance from domain knowledge: past damage,
  overhead service, a longer path, more or older wood poles, and a more overhead circuit can
  never *lower* risk. Any feature that comes out with the wrong sign is dropped, then the
  model is refit. λ is picked by 5-fold cross-validation grouped by circuit, inside Sep only
  (λ = 10,000; mean fold AUC 0.60).
- **Why a hybrid:** before Sep 2024 there are only 89 damage records on 29 circuits, so Sep
  can't teach the model how much past damage matters. In Sep training, all three history
  features scored *below* chance (AUC 0.44 to 0.49), so the sign rule dropped them. A5 provides
  that term: **served score = z(circuit past damage per 1k homes) + z(learned score)**, with
  equal weights chosen before testing. Score = exp(that sum), which is always positive, so
  `score × severity` works.
- **Test:** the Feb 2025 storm, with history taken from damage before Feb 12, 2025.
  This is the setup we serve.

### Results on Feb 2025 (117,595 homes with topology, 26,163 hit)
| candidate | AUC | High band (top 15%) catches | lift |
|---|---|---|---|
| A5 baseline: circuit past damage per 1k homes (prototype `final.py`) | 0.676 | 32.0% of hit homes | 2.13× |
| learned only (Sep-trained, no history) | 0.647 | 29.0% | 1.93× |
| **hybrid (served)** | **0.702** | **33.1%** | **2.21×** |

On the 78,550 homes that actually get a band (A6 not fallback): baseline 0.660 AUC / 1.59× lift,
learned 0.654 / 1.92×, **hybrid 0.695 / 2.03×**.
Sensitivity to the history weight (1.0 was fixed in advance): 0.5 → 0.688 AUC, 2.0 → 0.701.

**Plain summary for judges:** trained on one storm and checked on a later, different storm,
the High band holds about **2.2 times its share** of the homes that later lost power. The
learned part alone does *not* beat the simple "past damage on your circuit" rule (0.65 vs 0.68
AUC). Combining the two beats both. To be honest about it: we picked the served candidate
by comparing three options declared in advance on the Feb test, so the Feb numbers may be
slightly optimistic.

Learned weights (standardized): longer path +, more poles nearby (built-up areas) −, home on a
large main section −, overhead service +, wood share +, circuit size +. The home's own service
drop type barely matters (AUC 0.50 on both storms), because the label is about upstream
equipment, not the drop.

## Bands, confidence, fallback
- **Bands (A5):** cutoffs are fixed once over all homes at severity 0.8: top 15% High, next 25%
  Medium. At other severities, `score × severity` is compared with the same cutoffs, so a
  weaker storm can never raise a band.
- **Confidence (A6):** counts damage records on the home's circuit before Feb 12, 2025.
  - **High:** 3 or more records and a topology match. 55,000 homes, 41 circuits.
  - **Low:** 1 or 2 records. The band is still shown, with a "Limited history" note.
    23,550 homes, 21 circuits.
  - **Fallback:** 0 records (**39,045 homes, 48 circuits**) or no topology (47 homes). The
    response uses the exact `forecast_fallback.json` shape with the official outage link.
  - "medium" confidence is not used.
- **Factors:** the top 3 of coef × standardized value. The label describes the home (high or
  low value); the direction is how it moves risk. Strength: ≥ 0.5 strong, ≥ 0.2 medium, else
  weak (in standard-deviation units of the score).
- **rank_note:** the home's percentile among homes with topology, shown as "Higher than about
  N in 10" or "Lower than about M in 10".

## Limitations
- Only two storms, and they are different kinds (Sep: wind and rain; Feb: ice). Whether a home
  was hit in Sep barely predicts Feb at the home level (AUC 0.53).
- **33% of homes fall back** under the A6 rule, because 48 circuits have no damage records
  before Feb.
- The label depends on nearest-device mapping. 7% of records sit more than 250 m from their device.
- No weather, vegetation, or customer outage records. The ARCOS damage records stand in for outages.
- Pole age is missing for 21% of poles. Homes with no poles within 300 m use the average.

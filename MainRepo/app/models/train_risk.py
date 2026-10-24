"""Offline training + backtest for the Lane B risk model.

    .venv/bin/python -m app.models.train_risk            # rebuild features, train, backtest, write artifact + score cache
    .venv/bin/python -m app.models.train_risk --score    # only rebuild the per-home score cache from the artifact

Temporal validation, no peeking:
    TRAIN target = sep2024 storm, history features from damage before 2024-09-26.
    TEST  target = feb2025 storm, history features from damage before 2025-02-12.
The served model is the Sep-trained one, scored with pre-Feb history (honest for the Feb demo).
Writes app/models/artifacts/risk_model.json (coefficients, standardisation stats, band
cutoffs, metrics). No per-home data, ids or coordinates go in the artifact.
"""
from __future__ import annotations

import argparse
import json

import numpy as np

from app.models import risk_features as rf
from app.models.common import ARTIFACTS_DIR, DEFAULT_SEVERITY

ARTIFACT = ARTIFACTS_DIR / "risk_model.json"
TRAIN, TEST = "sep2024", "feb2025"
LAMBDAS = [0.1, 1.0, 10.0, 100.0, 1000.0, 10000.0]
HIGH_SHARE, MED_SHARE = 0.15, 0.25   # A5: top 15% High, next 25% Medium


# ------------------------------------------------------------------ model -------
def fit_logreg(X: np.ndarray, y: np.ndarray, lam: float, iters: int = 50) -> tuple[np.ndarray, float]:
    """L2-regularised logistic regression by Newton/IRLS (intercept unpenalised). Deterministic."""
    n, f = X.shape
    A = np.hstack([np.ones((n, 1)), X])
    w = np.zeros(f + 1)
    w[0] = np.log((y.mean() + 1e-9) / (1 - y.mean() + 1e-9))
    P = lam * np.eye(f + 1)
    P[0, 0] = 0.0
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-(A @ w)))
        g = A.T @ (p - y) + P @ w
        H = (A * (p * (1 - p))[:, None]).T @ A + P
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return w[1:], float(w[0])


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def _avg_ranks(s: np.ndarray) -> np.ndarray:
    _, inv, cnt = np.unique(s, return_inverse=True, return_counts=True)
    start = np.concatenate([[0], np.cumsum(cnt)[:-1]])
    return (start + (cnt + 1) / 2.0)[inv]


def auc(score: np.ndarray, y: np.ndarray) -> float:
    """Mann-Whitney AUC with ties counted as half."""
    r = _avg_ranks(score)
    npos = y.sum()
    nneg = len(y) - npos
    return float((r[y == 1].sum() - npos * (npos + 1) / 2) / (npos * nneg))


def top_share_captured(score: np.ndarray, y: np.ndarray, share: float) -> float:
    """Expected share of hit homes inside the top `share` of homes by score,
    breaking ties at the cut uniformly at random (exact expectation, no RNG)."""
    n = len(score)
    k = share * n
    vals, inv = np.unique(-score, return_inverse=True)   # descending groups
    g_n = np.bincount(inv).astype(float)
    g_pos = np.bincount(inv, weights=y.astype(float))
    taken = 0.0
    hits = 0.0
    for gn, gp in zip(g_n, g_pos):
        if taken + gn <= k:
            taken += gn
            hits += gp
        else:
            hits += gp * (k - taken) / gn
            break
    return float(hits / y.sum())


def evaluate(score, y) -> dict:
    cap = top_share_captured(score, y, HIGH_SHARE)
    cap40 = top_share_captured(score, y, HIGH_SHARE + MED_SHARE)
    return {
        "auc": round(auc(score, y), 4),
        "high_band_hit_share": round(cap, 4),
        "high_band_lift": round(cap / HIGH_SHARE, 3),
        "high_plus_medium_hit_share": round(cap40, 4),
        "n_homes": int(len(y)),
        "n_hit": int(y.sum()),
    }


# ----------------------------------------------------------- standardising ------
def impute(X: np.ndarray, means: np.ndarray) -> np.ndarray:
    X = X.copy()
    bad = ~np.isfinite(X)
    X[bad] = np.take(means, np.nonzero(bad)[1])
    return X


def col_stats(X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mu = np.nanmean(X, axis=0)
    sd = np.nanstd(X, axis=0)
    return mu, np.where(sd > 1e-9, sd, 1.0)


def standardize_for_target(Xraw: np.ndarray, train_mu, train_sd) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Static features use the training stats. History features are standardised within the
    scored set itself (its own history window), because pre-Sep and pre-Feb windows have
    very different lengths (89 vs 345 rows): what matters is 'more past damage than other
    homes', not the raw count. No labels are used."""
    mu, sd = train_mu.copy(), train_sd.copy()
    own_mu, own_sd = col_stats(Xraw)
    for j, (name, hist) in enumerate(rf.FEATURES):
        if hist:
            mu[j], sd[j] = own_mu[j], own_sd[j]
    Z = (impute(Xraw, mu) - mu) / sd
    return Z, mu, sd


# ------------------------------------------------------------------ fitting -----
# A-priori sign constraints (domain knowledge, fixed before looking at any result):
# more past damage, overhead service, a longer path, more wood / older poles and a more
# overhead circuit can never LOWER risk. A feature whose learned weight comes out with the
# wrong sign is dropped (weight 0) and the model is refit (active-set).
NONNEG = {"overhead", "path_len", "pole_wood_share", "pole_age", "circ_oh_share",
          "circ_dmg_per1k", "near_dmg", "path_prior_hits"}


def fit_signed(Z, y, lam, cols=None) -> tuple[np.ndarray, float]:
    names = rf.FEATURE_NAMES
    act = list(range(Z.shape[1])) if cols is None else list(cols)
    while True:
        w, b = fit_logreg(Z[:, act], y, lam)
        bad = [c for c, wi in zip(act, w) if names[c] in NONNEG and wi < 0]
        if not bad:
            break
        act = [c for c in act if c not in bad]
    W = np.zeros(Z.shape[1])
    W[act] = w
    return W, b


def choose_lambda(Z, y, groups) -> tuple[float, dict]:
    """5-fold CV grouped by circuit, inside the TRAIN storm only (never touches Feb).
    Scored as the mean of per-fold AUCs (pooling folds would mix fold intercepts)."""
    ug = np.unique(groups)
    fold_of = {g: i % 5 for i, g in enumerate(ug)}  # deterministic (sorted circuit order)
    fold = np.array([fold_of[g] for g in groups])
    res = {}
    for lam in LAMBDAS:
        aucs = []
        for k in range(5):
            tr, te = fold != k, fold == k
            if y[te].sum() == 0 or y[tr].sum() == 0:
                continue
            w, b = fit_signed(Z[tr], y[tr], lam)
            aucs.append(auc(Z[te] @ w + b, y[te].astype(int)))
        res[lam] = round(float(np.mean(aucs)), 4)
    best = max(LAMBDAS, key=lambda l: (res[l], l))
    return best, res


# ------------------------------------------------------------------ main --------
def train(verbose: bool = True) -> dict:
    """Pre-declared candidates, all evaluated once on Feb 2025:
      baseline : A5 heuristic, circuit past damage per 1k homes (prototype final.py)
      learned  : sign-constrained L2 logistic regression trained on Sep 2024 only
      hybrid   : z(circuit past damage per 1k homes) + z(learned score), equal weights.
                 Why: the pre-Sep record is only 89 rows on 29 circuits, so Sep cannot teach
                 the model how much past damage matters; A5 supplies that part and the
                 learned part ranks homes within and across circuits.
    Served = the candidate with the best Feb AUC (disclosed in the model card)."""
    log = print if verbose else (lambda *a, **k: None)
    feat = rf.load_features(rebuild=True, verbose=verbose)
    topo = feat["has_topo"].astype(bool)
    groups = feat["circ_index"][topo]
    names = rf.FEATURE_NAMES
    jc = names.index("circ_dmg_per1k")

    Xtr_raw = rf.design_matrix(feat, TRAIN)[topo]
    ytr = feat[f"label_{TRAIN}"][topo].astype(float)
    tr_mu, tr_sd = col_stats(Xtr_raw)
    Ztr, mu_tr, sd_tr = standardize_for_target(Xtr_raw, tr_mu, tr_sd)

    lam, cv = choose_lambda(Ztr, ytr, groups)
    log(f"grouped-CV mean per-fold AUC by lambda (train storm): {cv} -> lambda={lam}")
    w, b = fit_signed(Ztr, ytr, lam)
    log("learned coef: " + str({n: round(float(x), 3) for n, x in zip(names, w) if x}))

    Xte_raw = rf.design_matrix(feat, TEST)[topo]
    yte = feat[f"label_{TEST}"][topo].astype(int)
    Zte, mu_te, sd_te = standardize_for_target(Xte_raw, tr_mu, tr_sd)

    # hybrid as one linear score over standardised features (std units of each part)
    lin_tr = Ztr @ w
    s_static = float(lin_tr.std()) or 1.0
    hyb = w / s_static
    hyb[jc] += 1.0          # history part: z of log(1 + circuit past damage per 1k homes)

    cands = {
        "baseline": feat[f"baseline_{TEST}"][topo],
        "learned": Zte @ w + b,
        "hybrid": Zte @ hyb,
    }
    shown = feat[f"circ_rows_{TEST}"][topo] >= 1   # A6: homes that actually get a band
    metrics = {
        "test_storm": "Feb 2025 (learned part trained on Sep 2024 only)",
        "train_storm": "Sep 2024",
        "candidates_test_all_homes": {k: evaluate(v, yte) for k, v in cands.items()},
        "candidates_test_banded_homes": {k: evaluate(v[shown], yte[shown]) for k, v in cands.items()},
        "learned_train_in_sample": evaluate(Ztr @ w + b, ytr.astype(int)),
        "train_grouped_cv_auc": cv[lam],
        "cv_auc_by_lambda": {str(k): v for k, v in cv.items()},
        "lambda": lam,
        "single_feature_test_auc": {n: round(auc(Zte[:, j], yte), 4) for j, n in enumerate(names)},
        "single_feature_train_auc": {n: round(auc(Ztr[:, j], ytr.astype(int)), 4) for j, n in enumerate(names)},
    }
    # sensitivity: hybrid weight on the history part (reported only; 1.0 was fixed a priori)
    sens = {}
    for a in (0.5, 2.0):
        h2 = w / s_static
        h2[jc] += a
        sens[str(a)] = evaluate(Zte @ h2, yte)
    metrics["hybrid_history_weight_sensitivity"] = sens
    winner = max(cands, key=lambda k: metrics["candidates_test_all_homes"][k]["auc"])
    metrics["served"] = winner
    log(json.dumps({"all": metrics["candidates_test_all_homes"], "banded": metrics["candidates_test_banded_homes"]}, indent=1))
    log(f"served: {winner}")

    artifact = {
        "version": 2,
        "kind": "hybrid: A5 circuit history + sign-constrained L2 logistic regression (numpy)",
        "served": winner,
        "features": names,
        "history_features": rf.HISTORY_FEATURES,
        # served linear score over standardised features; score = exp(coef . z)
        "coef": [round(float(x), 6) for x in hyb],
        "transform": "exp",
        "learned_coef": [round(float(x), 6) for x in w],
        "learned_intercept": round(b, 6),
        "learned_score_std": round(s_static, 6),
        "nonneg_features": sorted(NONNEG),
        "train_target": TRAIN,
        "serve_target": TEST,
        # standardisation used when serving (static = train stats, history = pre-Feb window stats)
        "serve_mean": [round(float(x), 6) for x in mu_te],
        "serve_std": [round(float(x), 6) for x in sd_te],
        "train_mean": [round(float(x), 6) for x in mu_tr],
        "train_std": [round(float(x), 6) for x in sd_tr],
        "label": "home's upstream chain contains a device mapped from that storm's damage (A2 mapping)",
        "history_cutoffs": rf.TARGETS,
        "metrics": metrics,
    }
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    # cutoffs over all homes (with topology) at severity 0.8, from the served scores
    from app.models import risk
    scores = risk.served_scores(feat, artifact)[topo] * DEFAULT_SEVERITY
    hi = float(np.quantile(scores, 1 - HIGH_SHARE))
    med = float(np.quantile(scores, 1 - HIGH_SHARE - MED_SHARE))
    artifact["band_cutoffs"] = {"high": round(hi, 8), "medium": round(med, 8), "severity": DEFAULT_SEVERITY,
                                "rule": "score x severity >= high -> High; >= medium -> Medium; else Low"}
    with open(ARTIFACT, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=1)
    risk.load_artifact.cache_clear()
    log(f"wrote {ARTIFACT}")
    return artifact


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--score", action="store_true", help="only rebuild the per-home score cache")
    a = ap.parse_args()
    from app.models import risk
    if not a.score:
        train()
    stats = risk.build_cache(verbose=True)
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()

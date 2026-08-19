"""Train and evaluate the surrogate models.

    python app/train.py                 # full run
    python app/train.py --quick         # small run for a smoke test

Four artefacts land in ``backend/models``:

    orbit_impact_clf.pkl    P(strikes Earth) from six Keplerian elements
    orbit_distance_reg.pkl  log10 of the closest approach distance, AU
    effects_airburst_clf.pkl  does the body burst in the air or reach the ground
    effects_reg.pkl         eight damage quantities from the impactor properties

Gradient-boosted histogram trees are used throughout: they need no feature
scaling, handle the sentinel values on the discontinuous targets (a crater
diameter simply does not exist for an airburst) without special casing, and
train on a laptop CPU in minutes rather than hours.
"""
from __future__ import annotations

import argparse
import json
import os
import time

import joblib
import numpy as np
from sklearn.ensemble import (HistGradientBoostingClassifier,
                              HistGradientBoostingRegressor)
from sklearn.metrics import (average_precision_score, brier_score_loss,
                             mean_absolute_error, r2_score, roc_auc_score)
from sklearn.model_selection import train_test_split

import dataset

_HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(_HERE, "..", "models")
os.makedirs(MODEL_DIR, exist_ok=True)


def _save(obj, name):
    path = os.path.join(MODEL_DIR, name)
    joblib.dump(obj, path, compress=3)
    size = os.path.getsize(path) / 1e6
    print(f"    saved {name} ({size:.1f} MB)")


# ---------------------------------------------------------------------------
def train_orbit_models(n_orbits: int, seed: int = 7) -> dict:
    print("\n[1/2] Orbit impact model")
    X, y, meta, el = dataset.build_orbit_dataset(n_total=n_orbits, seed=seed)

    d_log = np.log10(np.maximum(meta["min_distance_au"], 1e-7))
    Xtr, Xte, ytr, yte, dtr, dte = train_test_split(
        X, y, d_log, test_size=0.2, random_state=seed, stratify=y)

    print("  fitting impact classifier...")
    t0 = time.time()
    clf = HistGradientBoostingClassifier(
        max_iter=500, learning_rate=0.06, max_leaf_nodes=63,
        min_samples_leaf=20, l2_regularization=1.0,
        early_stopping=True, validation_fraction=0.15, n_iter_no_change=30,
        random_state=seed)
    clf.fit(Xtr, ytr)
    p = clf.predict_proba(Xte)[:, 1]
    metrics = {
        "n_train": int(Xtr.shape[0]),
        "n_test": int(Xte.shape[0]),
        "positive_rate": float(y.mean()),
        "roc_auc": float(roc_auc_score(yte, p)),
        "pr_auc": float(average_precision_score(yte, p)),
        "brier": float(brier_score_loss(yte, p)),
        "iterations": int(clf.n_iter_),
        "fit_seconds": round(time.time() - t0, 1),
    }
    print(f"    ROC-AUC {metrics['roc_auc']:.4f}  PR-AUC {metrics['pr_auc']:.4f}"
          f"  Brier {metrics['brier']:.5f}  ({metrics['fit_seconds']}s,"
          f" {metrics['iterations']} trees)")

    # reliability: does a predicted 30% actually strike 30% of the time?
    bins = np.array([0.0, 0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 1.01])
    rel = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (p >= lo) & (p < hi)
        if m.sum() >= 20:
            rel.append({"bin": f"{lo:.2f}-{hi:.2f}", "n": int(m.sum()),
                        "predicted": round(float(p[m].mean()), 4),
                        "observed": round(float(yte[m].mean()), 4)})
    metrics["reliability"] = rel
    print("    calibration (predicted vs observed impact rate):")
    for r in rel:
        print(f"      {r['bin']:>10s}  n={r['n']:<6d} pred {r['predicted']:.3f}"
              f"  obs {r['observed']:.3f}")

    print("  fitting closest-approach distance regressor...")
    reg = HistGradientBoostingRegressor(
        max_iter=400, learning_rate=0.06, max_leaf_nodes=63,
        early_stopping=True, validation_fraction=0.15, n_iter_no_change=30,
        random_state=seed)
    reg.fit(Xtr, dtr)
    pred_d = reg.predict(Xte)
    metrics["distance_r2"] = float(r2_score(dte, pred_d))
    metrics["distance_mae_dex"] = float(mean_absolute_error(dte, pred_d))
    print(f"    R2 {metrics['distance_r2']:.4f}  MAE"
          f" {metrics['distance_mae_dex']:.3f} dex")

    _save(clf, "orbit_impact_clf.pkl")
    _save(reg, "orbit_distance_reg.pkl")
    return metrics


# ---------------------------------------------------------------------------
def train_effects_models(n_effects: int, seed: int = 11) -> dict:
    print("\n[2/2] Impact effects model")
    X, Y, airburst = dataset.build_effects_dataset(n=n_effects, seed=seed)

    Xtr, Xte, Ytr, Yte, atr, ate = train_test_split(
        X, Y, airburst, test_size=0.2, random_state=seed)

    print("  fitting airburst classifier...")
    clf = HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.08, max_leaf_nodes=63,
        early_stopping=True, validation_fraction=0.1, n_iter_no_change=20,
        random_state=seed)
    clf.fit(Xtr, atr)
    pa = clf.predict_proba(Xte)[:, 1]
    acc = float(((pa > 0.5).astype(int) == ate).mean())
    metrics = {"airburst_accuracy": acc,
               "airburst_roc_auc": float(roc_auc_score(ate, pa)),
               "n_train": int(Xtr.shape[0]), "targets": {}}
    print(f"    accuracy {acc:.4f}  ROC-AUC {metrics['airburst_roc_auc']:.4f}")

    print("  fitting damage regressors...")
    regressors = {}
    for j, name in enumerate(dataset.EFFECT_TARGETS):
        t0 = time.time()
        cond = dataset.CONDITIONAL_TARGETS.get(name)
        if cond == "airburst":
            mtr, mte = atr == 1, ate == 1
        elif cond == "ground":
            mtr, mte = atr == 0, ate == 0
        else:
            mtr = np.ones(len(atr), dtype=bool)
            mte = np.ones(len(ate), dtype=bool)

        r = HistGradientBoostingRegressor(
            max_iter=400, learning_rate=0.08, max_leaf_nodes=63,
            early_stopping=True, validation_fraction=0.1, n_iter_no_change=20,
            random_state=seed)
        r.fit(Xtr[mtr], Ytr[mtr, j])
        pred = r.predict(Xte[mte])
        r2 = float(r2_score(Yte[mte, j], pred))
        mae = float(mean_absolute_error(Yte[mte, j], pred))
        regressors[name] = r
        metrics["targets"][name] = {"r2": round(r2, 5), "mae": round(mae, 5),
                                    "conditional": cond, "n": int(mtr.sum()),
                                    "seconds": round(time.time() - t0, 1)}
        tag = f" [{cond} only]" if cond else ""
        print(f"    {name:26s} R2 {r2:7.4f}   MAE {mae:7.4f}{tag}")

    _save(clf, "effects_airburst_clf.pkl")
    _save({"targets": dataset.EFFECT_TARGETS, "models": regressors,
           "conditional": dataset.CONDITIONAL_TARGETS},
          "effects_reg.pkl")
    return metrics


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true",
                    help="small dataset, for verifying the pipeline runs")
    ap.add_argument("--orbits", type=int, default=60000)
    ap.add_argument("--effects", type=int, default=250000)
    ap.add_argument("--only", choices=["orbit", "effects"],
                    help="retrain just one family, keeping the other artefacts")
    args = ap.parse_args()

    n_orbits = 4000 if args.quick else args.orbits
    n_effects = 20000 if args.quick else args.effects

    t0 = time.time()
    prior = {}
    path = os.path.join(MODEL_DIR, "training_report.json")
    if args.only and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            prior = json.load(fh)

    report = {
        "orbit": (train_orbit_models(n_orbits) if args.only != "effects"
                  else prior.get("orbit")),
        "effects": (train_effects_models(n_effects) if args.only != "orbit"
                    else prior.get("effects")),
        "horizon_years": dataset.HORIZON_YEARS,
        "base_epoch_jd": dataset.JD_BASE,
        "orbit_features": dataset.ORBIT_FEATURES,
        "effect_features": dataset.EFFECT_FEATURES,
        "effect_targets": dataset.EFFECT_TARGETS,
        "total_seconds": None,
    }
    report["total_seconds"] = round(time.time() - t0, 1)

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"\nDone in {report['total_seconds']}s. Report -> {path}")


if __name__ == "__main__":
    main()

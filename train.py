"""Train and compare the models for every vehicle type.

    python build_dataset.py   # once, builds data/*.csv from data/raw/
    python train.py

For each vehicle type (bike & scooter, car, electric scooter) this trains
  - 6 regression models  -> predict mileage (km/l, or km/kWh)
  - 6 classification models -> predict the efficiency class (Thirsty / Balanced / Efficient)
saves every fitted pipeline to models/ and all the scores to models/metrics.json,
which the website reads to show every model's result.
"""
import json
import re
import time
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor, RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
)
from sklearn.model_selection import KFold, StratifiedKFold, cross_val_score, train_test_split
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

from features import CATEGORIES, CLASS_LABELS

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
MODEL_DIR = ROOT / "models"
SEED = 42


def regressors():
    return {
        "Linear Regression": LinearRegression(),
        "Ridge Regression": Ridge(alpha=1.0),
        "Decision Tree": DecisionTreeRegressor(max_depth=10, min_samples_leaf=2, random_state=SEED),
        "K-Nearest Neighbors": KNeighborsRegressor(n_neighbors=5, weights="distance"),
        "Random Forest": RandomForestRegressor(n_estimators=250, min_samples_leaf=1, n_jobs=-1, random_state=SEED),
        "Gradient Boosting": GradientBoostingRegressor(n_estimators=250, learning_rate=0.06, max_depth=3, subsample=0.9, random_state=SEED),
    }


def classifiers():
    return {
        "Logistic Regression": LogisticRegression(max_iter=3000),
        "Decision Tree": DecisionTreeClassifier(max_depth=8, min_samples_leaf=2, random_state=SEED),
        "K-Nearest Neighbors": KNeighborsClassifier(n_neighbors=5, weights="distance"),
        "Random Forest": RandomForestClassifier(n_estimators=250, n_jobs=-1, random_state=SEED),
        "Gradient Boosting": GradientBoostingClassifier(n_estimators=150, learning_rate=0.08, max_depth=3, random_state=SEED),
        "Support Vector Machine": SVC(kernel="rbf", C=3.0, probability=True, random_state=SEED),
    }


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def build_pipeline(model, categorical, numeric):
    pre = ColumnTransformer(
        [
            ("num", Pipeline([("fill", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric),
            ("cat", OneHotEncoder(handle_unknown="ignore"), categorical),
        ]
    )
    return Pipeline([("prep", pre), ("model", model)])


def regression_task(cat, cfg, X_train, X_test, y_train, y_test):
    rows, fitted = [], {}
    cv = KFold(5, shuffle=True, random_state=SEED)
    for name, model in regressors().items():
        pipe = build_pipeline(model, cfg["categorical"], cfg["numeric"])
        t0 = time.perf_counter()
        pipe.fit(X_train, y_train)
        seconds = time.perf_counter() - t0
        pred = pipe.predict(X_test)
        scores = cross_val_score(build_pipeline(regressors()[name], cfg["categorical"], cfg["numeric"]), X_train, y_train, cv=cv, scoring="r2")
        rows.append(
            {
                "name": name,
                "slug": slug(name),
                "train_r2": round(float(r2_score(y_train, pipe.predict(X_train))), 4),
                "r2": round(float(r2_score(y_test, pred)), 4),
                "mae": round(float(mean_absolute_error(y_test, pred)), 3),
                "rmse": round(float(np.sqrt(mean_squared_error(y_test, pred))), 3),
                "cv_r2": round(float(scores.mean()), 4),
                "cv_std": round(float(scores.std()), 4),
                "fit_seconds": round(seconds, 2),
            }
        )
        fitted[name] = pipe
        joblib.dump(pipe, MODEL_DIR / f"{cat}__reg__{slug(name)}.joblib", compress=3)
        print(f"  [{cat}] regression     {name:<24} train R2={rows[-1]['train_r2']:.3f}  test R2={rows[-1]['r2']:.3f}  CV R2={rows[-1]['cv_r2']:.3f}")

    # The best model is the one that generalises best across folds, which is steadier than a
    # single small test split (the electric scooter set has only 42 rows).
    rows.sort(key=lambda r: r["cv_r2"], reverse=True)
    best = rows[0]["name"]

    features = cfg["features"]
    importance_all, predicted_all = {}, {}
    for name, pipe in fitted.items():
        imp = permutation_importance(pipe, X_test, y_test, n_repeats=10, random_state=SEED, n_jobs=-1)
        importance_all[name] = sorted(
            ({"feature": f, "value": round(float(v), 4)} for f, v in zip(features, imp.importances_mean)),
            key=lambda d: d["value"],
            reverse=True,
        )
        predicted_all[name] = [round(float(v), 2) for v in pipe.predict(X_test)]
    return {
        "models": rows,
        "best": best,
        "importance": importance_all[best],
        "importance_all": importance_all,
        "scatter": {
            "actual": [round(float(v), 2) for v in y_test],
            "predicted": predicted_all[best],
            "predicted_all": predicted_all,
        },
    }


def classification_task(cat, cfg, X_train, X_test, c_train, c_test):
    rows, fitted = [], {}
    cv = StratifiedKFold(5, shuffle=True, random_state=SEED)
    for name, model in classifiers().items():
        pipe = build_pipeline(model, cfg["categorical"], cfg["numeric"])
        t0 = time.perf_counter()
        pipe.fit(X_train, c_train)
        seconds = time.perf_counter() - t0
        pred = pipe.predict(X_test)
        scores = cross_val_score(build_pipeline(classifiers()[name], cfg["categorical"], cfg["numeric"]), X_train, c_train, cv=cv, scoring="accuracy")
        rows.append(
            {
                "name": name,
                "slug": slug(name),
                "train_accuracy": round(float(accuracy_score(c_train, pipe.predict(X_train))), 4),
                "accuracy": round(float(accuracy_score(c_test, pred)), 4),
                "precision": round(float(precision_score(c_test, pred, average="macro", zero_division=0)), 4),
                "recall": round(float(recall_score(c_test, pred, average="macro", zero_division=0)), 4),
                "f1": round(float(f1_score(c_test, pred, average="macro", zero_division=0)), 4),
                "cv_accuracy": round(float(scores.mean()), 4),
                "cv_std": round(float(scores.std()), 4),
                "fit_seconds": round(seconds, 2),
            }
        )
        fitted[name] = pipe
        joblib.dump(pipe, MODEL_DIR / f"{cat}__clf__{slug(name)}.joblib", compress=3)
        print(f"  [{cat}] classification {name:<24} train acc={rows[-1]['train_accuracy']:.3f}  test acc={rows[-1]['accuracy']:.3f}  CV acc={rows[-1]['cv_accuracy']:.3f}")

    rows.sort(key=lambda r: r["cv_accuracy"], reverse=True)
    best = rows[0]["name"]
    matrices = {name: confusion_matrix(c_test, pipe.predict(X_test), labels=CLASS_LABELS).tolist() for name, pipe in fitted.items()}
    return {
        "models": rows,
        "best": best,
        "confusion": {"labels": CLASS_LABELS, "matrix": matrices[best], "all": matrices},
    }


def run_category(cat, cfg):
    df = pd.read_csv(DATA_DIR / cfg["file"])
    target = cfg["target"]
    features = cfg["features"]
    df = df.dropna(subset=[target]).reset_index(drop=True)

    q1, q2 = (float(v) for v in df[target].quantile([1 / 3, 2 / 3]))
    classes = pd.cut(df[target], [-np.inf, q1, q2, np.inf], labels=CLASS_LABELS).astype(str)

    X, y = df[features], df[target]
    X_train, X_test, y_train, y_test, c_train, c_test = train_test_split(X, y, classes, test_size=0.2, random_state=SEED, stratify=classes)

    print(f"{cfg['label']}: {len(df)} rows ({len(X_train)} train / {len(X_test)} test)")
    reg = regression_task(cat, cfg, X_train, X_test, y_train, y_test)
    clf = classification_task(cat, cfg, X_train, X_test, c_train, c_test)

    return {
        "label": cfg["label"],
        "unit": cfg["unit"],
        "target": target,
        "rows": int(len(df)),
        "train_rows": int(len(X_train)),
        "test_rows": int(len(X_test)),
        "features": features,
        "target_range": [round(float(y.min()), 2), round(float(y.max()), 2)],
        "target_mean": round(float(y.mean()), 2),
        "thresholds": [round(q1, 2), round(q2, 2)],
        "feature_ranges": {f: [float(df[f].min()), float(df[f].max())] for f in cfg["numeric"]},
        "regression": reg,
        "classification": clf,
    }


def main():
    MODEL_DIR.mkdir(exist_ok=True)
    for old in MODEL_DIR.glob("*.joblib"):
        old.unlink()
    for cat, cfg in CATEGORIES.items():
        if not (DATA_DIR / cfg["file"]).exists():
            import build_dataset

            print("Building datasets from data/raw ...")
            build_dataset.main()
            break

    out = {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "categories": {}}
    for cat, cfg in CATEGORIES.items():
        out["categories"][cat] = run_category(cat, cfg)

    (MODEL_DIR / "metrics.json").write_text(json.dumps(out, indent=2))
    print("Done.")
    for cat, m in out["categories"].items():
        print(f"  {m['label']:<18} best regressor: {m['regression']['best']:<20} best classifier: {m['classification']['best']}")


if __name__ == "__main__":
    main()

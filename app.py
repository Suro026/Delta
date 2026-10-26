"""Delta - vehicle mileage and trip cost predictor (Flask).

    python app.py        ->  http://127.0.0.1:5000

On first run it builds the datasets and trains the models if they are missing.
"""
import json
import os
import secrets
import sqlite3
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

import joblib
import pandas as pd
from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, session, url_for

from features import (
    AC_FACTOR,
    AGE_PENALTY_PER_YEAR,
    CATEGORIES,
    CLASS_LABELS,
    FEATURE_NAMES,
    FUEL_FACTOR,
    FUEL_UNIT,
    ROAD_FACTOR,
    SERVICE_OVERDUE_FACTOR,
    real_world_factor,
)

ROOT = Path(__file__).parent
MODEL_DIR = ROOT / "models"
DATA_DIR = ROOT / "data"
# On Vercel the project folder is read-only and only /tmp can be written, so the history
# database lives there (it is cleared when the serverless instance is recycled).
if os.environ.get("VERCEL"):
    DB_PATH = Path(tempfile.gettempdir()) / "milemind.db"
else:
    DB_PATH = ROOT / "milemind.db"

# Static files sit in public/static so Vercel serves them from its CDN; the URL stays /static/...
app = Flask(__name__, static_folder=str(ROOT / "public" / "static"), static_url_path="/static")
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024


# --------------------------------------------------------------------- models
def load_models():
    if not (MODEL_DIR / "metrics.json").exists():
        import train

        train.main()
    metrics = json.loads((MODEL_DIR / "metrics.json").read_text())
    models = {}
    for cat, m in metrics["categories"].items():
        models[cat] = {
            "reg": {r["slug"]: joblib.load(MODEL_DIR / f"{cat}__reg__{r['slug']}.joblib") for r in m["regression"]["models"]},
            "clf": {r["slug"]: joblib.load(MODEL_DIR / f"{cat}__clf__{r['slug']}.joblib") for r in m["classification"]["models"]},
        }
    return metrics, models


def load_catalog():
    """Brands and models from the real datasets, used to pre-fill the form."""
    catalog = {}
    for cat, cfg in CATEGORIES.items():
        df = pd.read_csv(DATA_DIR / cfg["file"])
        medians = df[cfg["numeric"]].median()
        brands = {}
        for _, row in df.iterrows():
            entry = {"model": str(row["model"]), "listed": round(float(row[cfg["target"]]), 2)}
            for key in cfg["numeric"]:
                value = row[key] if pd.notna(row[key]) else medians[key]
                entry[key] = round(float(value), 2)
            for key in cfg["categorical"]:
                if key != "brand":
                    entry[key] = str(row[key])
            brands.setdefault(str(row["brand"]), []).append(entry)
        # Brands with a single oddly named row are noise in a drop-down.
        brands = {b: sorted(v, key=lambda e: e["model"]) for b, v in brands.items() if b and b.lower() not in ("hi", "capri", "khakhi")}
        catalog[cat] = dict(sorted(brands.items()))
    return catalog


METRICS, MODELS = load_models()
CATALOG = load_catalog()

PUBLIC_CONFIG = {
    cat: {
        "label": cfg["label"],
        "unit": cfg["unit"],
        "price_label": cfg["price_label"],
        "price_unit": cfg["price_unit"],
        "fuels": cfg["fuels"],
        "specs": cfg["specs"],
        "choices": cfg["choices"],
        "default": cfg["default"],
    }
    for cat, cfg in CATEGORIES.items()
}


# ------------------------------------------------------------------- database
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    columns = [r[1] for r in db.execute("PRAGMA table_info(history)")]
    if columns and "vehicle" not in columns:  # table left by the first version of the app
        db.execute("DROP TABLE history")
    db.execute("DROP TABLE IF EXISTS fuel_prices")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            vehicle TEXT NOT NULL,
            brand TEXT NOT NULL,
            model TEXT NOT NULL,
            fuel TEXT NOT NULL,
            road_type TEXT NOT NULL,
            distance_km REAL NOT NULL,
            price REAL NOT NULL,
            mileage REAL NOT NULL,
            unit TEXT NOT NULL,
            cost REAL NOT NULL,
            efficiency TEXT NOT NULL
        )
        """
    )
    db.commit()
    db.close()


init_db()


# ------------------------------------------------------------------ security
@app.before_request
def make_csrf_token():
    session.setdefault("csrf", secrets.token_hex(16))


def check_csrf():
    sent = request.form.get("csrf", "")
    if not sent or not secrets.compare_digest(sent, session.get("csrf", "")):
        abort(400, "Your session expired. Reload the page and try again.")


app.jinja_env.globals["csrf_token"] = lambda: session.get("csrf", "")


@app.template_filter("inr")
def inr(value, decimals=0):
    """Rupee amount with Indian digit grouping: 1,23,456.50"""
    value = float(value)
    sign = "-" if value < 0 else ""
    whole, _, frac = f"{abs(value):.{decimals}f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    return f"{sign}₹{whole}" + (f".{frac}" if decimals else "")


@app.after_request
def security_headers(resp):
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "same-origin"
    return resp


# ----------------------------------------------------------------- validation
class InputError(ValueError):
    pass


def _number(data, key, label, lo, hi, integer=False):
    raw = data.get(key)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise InputError(f"{label} must be a number.")
    if value != value or value in (float("inf"), float("-inf")):
        raise InputError(f"{label} must be a number.")
    if not lo <= value <= hi:
        raise InputError(f"{label} must be between {lo:g} and {hi:g}.")
    return int(round(value)) if integer else value


def _choice(data, key, label, options):
    value = data.get(key)
    if value not in options:
        raise InputError(f"{label} must be one of: {', '.join(map(str, options))}.")
    return value


def _flag(data, key):
    return str(data.get(key)).lower() in ("1", "true", "on")


def parse_payload(data):
    if not isinstance(data, dict):
        raise InputError("Send the form fields as a JSON object.")
    vehicle = _choice(data, "vehicle", "Vehicle type", list(CATEGORIES))
    cfg = CATEGORIES[vehicle]

    brand = str(data.get("brand", "")).strip()
    if not 1 <= len(brand) <= 40:
        raise InputError("Choose a brand (or type your own).")
    p = {
        "vehicle": vehicle,
        "brand": brand,
        "model": str(data.get("model", "")).strip()[:60] or "Custom",
        "fuel": _choice(data, "fuel", "Fuel", list(cfg["fuels"])),
        "road_type": _choice(data, "road_type", "Road type", list(ROAD_FACTOR)),
        "load_kg": _number(data, "load_kg", "Rider and load weight", 0, 600, integer=True),
        "vehicle_age": _number(data, "vehicle_age", "Vehicle age", 0, 30, integer=True),
        "ac_on": vehicle == "car" and _flag(data, "ac_on"),
        "service_overdue": _flag(data, "service_overdue"),
        "distance_km": _number(data, "distance_km", "Trip distance", 0.5, 5000),
        "days_per_month": _number({"d": data.get("days_per_month", 26)}, "d", "Days per month", 1, 31, integer=True),
    }
    price_hi = 100 if vehicle == "escooter" else 300
    p["price"] = _number(data, "price", cfg["price_label"], 0.5, price_hi)
    for spec in cfg["specs"]:
        p[spec["key"]] = _number(data, spec["key"], spec["label"], spec["min"], spec["max"], integer=spec["step"] == 1)
    for key, options in cfg["choices"].items():
        p[key] = _choice(data, key, key.title(), list(options))
    return p


def range_warnings(p, m):
    warnings = []
    for key, (lo, hi) in m["feature_ranges"].items():
        if not lo <= p[key] <= hi:
            label = FEATURE_NAMES.get(key, key)
            warnings.append(f"{label} of {p[key]:g} is outside the {lo:g}–{hi:g} range the models were trained on, so treat the result as rough.")
    if p["vehicle"] == "car":
        warnings.append("The car data are 1970–82 vehicles, so modern cars will usually do better than the rated figure shown.")
    if p["vehicle"] == "escooter":
        warnings.append("The electric scooter data has only 42 models, so the predictions are less certain.")
    return warnings[:4]


# ----------------------------------------------------------------- prediction
def run_prediction(p):
    cfg = CATEGORIES[p["vehicle"]]
    m = METRICS["categories"][p["vehicle"]]
    models = MODELS[p["vehicle"]]
    lo, hi = m["target_range"]

    frame = pd.DataFrame([{f: p[f] if f != "brand" else p["brand"] for f in cfg["features"]}], columns=cfg["features"])
    price_unit, mileage_unit = FUEL_UNIT[p["fuel"]]
    distance, price = p["distance_km"], p["price"]
    factor = real_world_factor(p["vehicle"], p["fuel"], p["road_type"], p["load_kg"], p["ac_on"], p["service_overdue"], p["vehicle_age"])

    def cost_for(mileage):
        return round(distance / mileage * price, 2)

    # 1. Regression: every model predicts the rated mileage; the real-road estimate applies the factor.
    best_reg = m["regression"]["best"]
    reg_rows = []
    for r in m["regression"]["models"]:
        rated = float(min(max(models["reg"][r["slug"]].predict(frame)[0], 0.7 * lo), 1.3 * hi))
        real = rated * factor
        reg_rows.append(
            {
                "name": r["name"],
                "rated": round(rated, 2),
                "real": round(real, 2),
                "cost": cost_for(real),
                "cost_per_km": round(price / real, 2),
                "r2": r["r2"],
                "mae": r["mae"],
                "rmse": r["rmse"],
                "cv_r2": r["cv_r2"],
                "is_best": r["name"] == best_reg,
            }
        )
    best = next(r for r in reg_rows if r["is_best"])

    # 2. Classification: every model votes on the efficiency class.
    best_clf = m["classification"]["best"]
    clf_rows = []
    for r in m["classification"]["models"]:
        pipe = models["clf"][r["slug"]]
        label = str(pipe.predict(frame)[0])
        proba = pipe.predict_proba(frame)[0]
        clf_rows.append(
            {
                "name": r["name"],
                "label": label,
                "confidence": round(float(max(proba)) * 100),
                "accuracy": r["accuracy"],
                "f1": r["f1"],
                "cv_accuracy": r["cv_accuracy"],
                "is_best": r["name"] == best_clf,
            }
        )
    votes = Counter(r["label"] for r in clf_rows)
    top = votes.most_common()
    best_label = next(r["label"] for r in clf_rows if r["is_best"])
    consensus = best_label if len(top) > 1 and top[0][1] == top[1][1] else top[0][0]

    # 3. What the same vehicle would cost on each type of road (best regression model).
    roads = []
    for road in ROAD_FACTOR:
        f = real_world_factor(p["vehicle"], p["fuel"], road, p["load_kg"], p["ac_on"], p["service_overdue"], p["vehicle_age"])
        real = best["rated"] * f
        roads.append({"road": road, "mileage": round(real, 2), "cost": cost_for(real), "selected": road == p["road_type"]})

    # 4. The dataset's own figure, when the user picked a real model from the list.
    listed = None
    for entry in CATALOG[p["vehicle"]].get(p["brand"], []):
        if entry["model"] == p["model"]:
            listed = entry["listed"]
            break

    costs = [r["cost"] for r in reg_rows]
    reals = [r["real"] for r in reg_rows]
    return {
        "inputs": p,
        "unit": mileage_unit,
        "price_unit": price_unit,
        "fuel_label": cfg["fuels"][p["fuel"]],
        "factor": round(factor, 3),
        "summary": {
            "best_model": best["name"],
            "rated": best["rated"],
            "real": best["real"],
            "cost": best["cost"],
            "cost_per_km": best["cost_per_km"],
            "cost_min": min(costs),
            "cost_max": max(costs),
            "real_min": min(reals),
            "real_max": max(reals),
            "listed": listed,
            "distance": distance,
            "price": price,
            "fuel_used": round(distance / best["real"], 2),
            "days_per_month": p["days_per_month"],
            "km_per_month": round(distance * p["days_per_month"], 1),
            "monthly": round(best["cost"] * p["days_per_month"], 2),
            "yearly": round(best["cost"] * p["days_per_month"] * 12, 2),
        },
        "regression": reg_rows,
        "classification": {
            "models": clf_rows,
            "consensus": consensus,
            "votes": {label: votes.get(label, 0) for label in CLASS_LABELS},
            "thresholds": m["thresholds"],
        },
        "roads": roads,
        "scale": {"min": m["target_range"][0], "max": m["target_range"][1], "thresholds": m["thresholds"], "unit": cfg["unit"], "rows": m["rows"]},
        "warnings": range_warnings(p, m),
    }


def save_history(result):
    p, s = result["inputs"], result["summary"]
    db = get_db()
    db.execute(
        """INSERT INTO history (created_at, vehicle, brand, model, fuel, road_type, distance_km, price, mileage, unit, cost, efficiency)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            p["vehicle"],
            p["brand"],
            p["model"],
            p["fuel"],
            p["road_type"],
            p["distance_km"],
            p["price"],
            s["real"],
            result["unit"],
            s["cost"],
            result["classification"]["consensus"],
        ),
    )
    db.execute("DELETE FROM history WHERE id NOT IN (SELECT id FROM history ORDER BY id DESC LIMIT 200)")
    db.commit()


# --------------------------------------------------------------------- pages
def sample_payload():
    """A real scooter from the dataset, for the home page demo."""
    entries = CATALOG["bike"].get("Honda") or next(iter(CATALOG["bike"].values()))
    entry = next((e for e in entries if e.get("category") == "scooter"), entries[0])
    p = {
        "vehicle": "bike",
        "brand": next(b for b, v in CATALOG["bike"].items() if entry in v),
        "model": entry["model"],
        "fuel": "petrol",
        "road_type": "city",
        "load_kg": 75,
        "vehicle_age": 2,
        "service_overdue": 0,
        "distance_km": 18,
        "price": 100,
    }
    for key in ("engine_cc", "power_ps", "torque_nm", "cylinders", "gears", "category", "cooling"):
        p[key] = entry[key]
    return p


@app.route("/")
def index():
    sample = run_prediction(parse_payload(sample_payload()))
    counts = {cat: m["rows"] for cat, m in METRICS["categories"].items()}
    return render_template("index.html", sample=sample, metrics=METRICS, counts=counts, page="home")


@app.route("/predict")
def predict_page():
    return render_template("predict.html", page="predict", config=PUBLIC_CONFIG, catalog=CATALOG, ranges={c: m["feature_ranges"] for c, m in METRICS["categories"].items()})


@app.post("/api/predict")
def api_predict():
    if not request.is_json:
        return jsonify(error="Send the request as JSON."), 415
    try:
        result = run_prediction(parse_payload(request.get_json(silent=True)))
    except InputError as exc:
        return jsonify(error=str(exc)), 400
    save_history(result)
    return jsonify(result)


@app.route("/results")
def results_page():
    return render_template("results.html", metrics=METRICS, names=FEATURE_NAMES, page="results")


@app.route("/history")
def history_page():
    rows = get_db().execute("SELECT * FROM history ORDER BY id DESC LIMIT 50").fetchall()
    return render_template("history.html", rows=rows, categories=CATEGORIES, page="history")


@app.post("/history/clear")
def history_clear():
    check_csrf()
    db = get_db()
    db.execute("DELETE FROM history")
    db.commit()
    flash("History cleared.", "ok")
    return redirect(url_for("history_page"))


@app.route("/about")
def about_page():
    return render_template(
        "about.html",
        metrics=METRICS,
        page="about",
        road=ROAD_FACTOR,
        cars=CATEGORIES,
        age_penalty=AGE_PENALTY_PER_YEAR,
        service=SERVICE_OVERDUE_FACTOR,
        ac=AC_FACTOR,
        fuel_factor=FUEL_FACTOR,
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False)

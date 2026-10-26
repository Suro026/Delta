"""Build the three clean training tables from the raw files in data/raw/.

    python build_dataset.py

    bikes.csv   motorcycles and scooters (Indian market) - listed mileage in km/l
    cars.csv    classic Auto-MPG cars                      - mileage converted to km/l
    escoot.csv  electric scooters                          - efficiency in km per kWh
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data"

MPG_TO_KMPL = 0.425144
CUBIC_INCH_TO_CC = 16.3871
LB_TO_KG = 0.453592

TWO_WORD_BRANDS = ("Royal Enfield", "Harley Davidson", "Harley-Davidson", "Moto Guzzi", "Moto Morini", "Ultraviolette")


# ------------------------------------------------------------------------ bikes
def _brand_model(name: str):
    name = name.strip()
    for brand in TWO_WORD_BRANDS:
        if name.lower().startswith(brand.lower()):
            return brand.replace("Harley Davidson", "Harley-Davidson"), name[len(brand):].strip()
    first, _, rest = name.partition(" ")
    return first, rest.strip()


def _first(cells, pattern, flags=re.I):
    for cell in cells:
        m = re.search(pattern, cell, flags)
        if m:
            return m
    return None


def build_bikes() -> pd.DataFrame:
    raw = pd.read_csv(RAW / "Bike_Features.csv", dtype=str)
    rows = []
    for _, r in raw.iterrows():
        cells = [str(c).strip() for c in r.tolist() if isinstance(c, str) and c.strip()]
        name = str(r["variant_name"]).strip()
        if not name or name == "nan":
            continue

        # The source file has shifted columns in many rows, so each value is found by
        # what it looks like (e.g. "155 cc", "12 Nm", "55 kmpl") instead of by column.
        mileage = re.search(r"([\d.]+)\s*kmpl", str(r["City Mileage"]), re.I)
        cc = _first(cells, r"^([\d.]+)\s*cc$")
        if not mileage or not cc:
            continue
        power = _first(cells, r"^([\d.]+)\s*(?:PS|bhp)\b")
        torque = _first(cells, r"^([\d.]+)\s*Nm")
        engine_text = str(r["Engine Type"]).lower()
        blob = " ".join(cells).lower()

        if re.search(r"single|1 cylinder", engine_text):
            cylinders = 1
        elif re.search(r"twin|parallel|2 cylinder|v-?2", engine_text):
            cylinders = 2
        elif re.search(r"triple|3 cylinder", engine_text):
            cylinders = 3
        elif re.search(r"four|inline 4|4 cylinder|v4|v-4", engine_text):
            cylinders = 4
        else:
            cylinders = np.nan

        cooling = "liquid" if "liquid" in blob else "oil" if "oil cooled" in blob or "oil-cooled" in blob else "air" if "air" in blob else "unknown"
        scooter = bool(re.search(r"\bcvt\b|automatic|v-belt|variomatic", blob))
        gears = _first(cells, r"^(\d)\s*speed")

        brand, model = _brand_model(name)
        value = float(mileage.group(1))
        displacement = float(cc.group(1))
        if not (10 <= value <= 120) or not (50 <= displacement <= 2500):
            continue
        rows.append(
            {
                "brand": brand,
                "model": model,
                "category": "scooter" if scooter else "motorcycle",
                "engine_cc": round(displacement, 1),
                "power_ps": float(power.group(1)) if power else np.nan,
                "torque_nm": float(torque.group(1)) if torque else np.nan,
                "cylinders": cylinders,
                "cooling": cooling,
                "gears": 1 if scooter else (float(gears.group(1)) if gears else np.nan),
                "price_inr": float(r["On-road prize"]) if pd.notna(r["On-road prize"]) else np.nan,
                "mileage_kmpl": value,
            }
        )
    df = pd.DataFrame(rows)
    # Same model sold in many colours: keep one row per brand + model + cc + mileage.
    df["model"] = df["model"].str.replace(r"\s+(Metallic|Matte|Dual Tone|Pearl|Black|Red|Blue|White|Grey|Gray|Silver|Green|Orange|Yellow)\b.*$", "", regex=True)
    # Variants that differ only in colour, wheels or brakes have identical specs and mileage.
    # Keep one of each, otherwise near-copies land in both the training and the test set
    # and make the scores look better than they are.
    spec_cols = ["brand", "category", "engine_cc", "power_ps", "torque_nm", "cylinders", "gears", "cooling", "mileage_kmpl"]
    df = df.drop_duplicates(subset=spec_cols).reset_index(drop=True)
    return df


# ------------------------------------------------------------------------- cars
def build_cars() -> pd.DataFrame:
    raw = pd.read_csv(RAW / "mpg_raw.csv")
    raw["horsepower"] = pd.to_numeric(raw["horsepower"], errors="coerce")
    names = raw["name"].str.strip().str.lower()
    fix = {"chevroelt": "chevrolet", "chevy": "chevrolet", "maxda": "mazda", "toyouta": "toyota", "vokswagen": "volkswagen", "vw": "volkswagen", "mercedes benz": "mercedes-benz"}
    for bad, good in fix.items():
        names = names.str.replace(rf"^{re.escape(bad)}\b", good, regex=True)
    brand = names.str.split().str[0]
    model = names.str.split(n=1).str[1].fillna("").str.strip()
    model = model.where(model != "", "(standard)")
    df = pd.DataFrame(
        {
            "brand": brand.str.title(),
            "model": model.str.title(),
            "fuel": np.where(names.str.contains("diesel"), "diesel", "petrol"),
            "cylinders": raw["cylinders"],
            "engine_cc": (raw["displacement"] * CUBIC_INCH_TO_CC).round(0),
            "power_hp": raw["horsepower"],
            "weight_kg": (raw["weight"] * LB_TO_KG).round(0),
            "acceleration_s": raw["acceleration"],
            "mileage_kmpl": (raw["mpg"] * MPG_TO_KMPL).round(2),
        }
    )
    # Only 7 diesel rows exist, too few to learn from: train on petrol cars and treat
    # diesel / CNG as a documented adjustment on top (see features.FUEL_FACTOR).
    return df[df["fuel"] == "petrol"].drop(columns="fuel").reset_index(drop=True)


# --------------------------------------------------------------------- scooters
def build_escoot() -> pd.DataFrame:
    raw = pd.read_excel(RAW / "Electric scooter - dataset.xlsx")
    kwh = raw["Electric voltage [V]"] * raw["Battery capacity [Ah]"] / 1000
    df = pd.DataFrame(
        {
            "brand": raw["Manufacturer"].astype(str).str.strip(),
            "model": raw["Model"].fillna(raw["Full name"]).astype(str).str.strip(),
            "motors": raw["Number of engines"],
            "power_w": raw["Total nominal power [W]"],
            "voltage_v": raw["Electric voltage [V]"],
            "battery_kwh": kwh.round(3),
            "weight_kg": raw["Weight [kg]"],
            "max_speed_kph": raw["Maximum speed [kph]"],
            "tire_in": raw["Tire size [in]"],
            "price_pln": raw["Price (gross, PLN)"],
            "range_km": raw["Range [km]"],
        }
    )
    df["km_per_kwh"] = (df["range_km"] / df["battery_kwh"]).round(2)
    df = df[(df["battery_kwh"] > 0) & df["km_per_kwh"].between(1, 500)].reset_index(drop=True)
    return df


def main():
    bikes, cars, escoot = build_bikes(), build_cars(), build_escoot()
    bikes.to_csv(OUT / "bikes.csv", index=False)
    cars.to_csv(OUT / "cars.csv", index=False)
    escoot.to_csv(OUT / "escoot.csv", index=False)
    print(f"bikes.csv   {len(bikes):>4} rows  ({bikes['brand'].nunique()} brands, {(bikes['category'] == 'scooter').sum()} scooters)")
    print(f"cars.csv    {len(cars):>4} rows  ({cars['brand'].nunique()} brands)")
    print(f"escoot.csv  {len(escoot):>4} rows  ({escoot['brand'].nunique()} brands)")


if __name__ == "__main__":
    main()

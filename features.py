"""Shared definitions for Delta.

Training and the website both import from here, so the columns the models are
trained on are always the columns the website sends.
"""

# Efficiency classes: the target is cut into three equal-sized groups per vehicle type.
CLASS_LABELS = ["Thirsty", "Balanced", "Efficient"]


def _spec(key, label, unit, lo, hi, step, hint=""):
    return {"key": key, "label": label, "unit": unit, "min": lo, "max": hi, "step": step, "hint": hint}


CATEGORIES = {
    "bike": {
        "label": "Bike & scooter",
        "file": "bikes.csv",
        "target": "mileage_kmpl",
        "unit": "km/l",
        "price_label": "Petrol price",
        "price_unit": "litre",
        "fuels": {"petrol": "Petrol"},
        "numeric": ["engine_cc", "power_ps", "torque_nm", "cylinders", "gears"],
        "categorical": ["brand", "category", "cooling"],
        "choices": {
            "category": {"motorcycle": "Motorcycle", "scooter": "Scooter"},
            "cooling": {"air": "Air cooled", "oil": "Oil cooled", "liquid": "Liquid cooled"},
        },
        "specs": [
            _spec("engine_cc", "Engine size", "cc", 50, 2500, 1),
            _spec("power_ps", "Max power", "PS", 3, 320, 0.1),
            _spec("torque_nm", "Max torque", "Nm", 4, 230, 0.1),
            _spec("cylinders", "Cylinders", "", 1, 6, 1),
            _spec("gears", "Gears", "", 1, 8, 1, "Scooters are 1 (automatic)"),
        ],
        "load_penalty": 0.06,
        "default": {"brand": "Honda", "category": "scooter", "cooling": "air"},
    },
    "car": {
        "label": "Car",
        "file": "cars.csv",
        "target": "mileage_kmpl",
        "unit": "km/l",
        "price_label": "Fuel price",
        "price_unit": "litre",
        "fuels": {"petrol": "Petrol", "diesel": "Diesel", "cng": "CNG"},
        "numeric": ["engine_cc", "cylinders", "power_hp", "weight_kg", "acceleration_s"],
        "categorical": ["brand"],
        "choices": {},
        "specs": [
            _spec("engine_cc", "Engine size", "cc", 600, 8000, 1),
            _spec("cylinders", "Cylinders", "", 2, 12, 1),
            _spec("power_hp", "Max power", "hp", 30, 600, 1),
            _spec("weight_kg", "Kerb weight", "kg", 500, 3500, 1),
            _spec("acceleration_s", "0-100 km/h", "s", 3, 30, 0.1, "Time to reach 100 km/h"),
        ],
        "load_penalty": 0.04,
        "default": {"brand": "Toyota"},
    },
    "escooter": {
        "label": "Electric scooter",
        "file": "escoot.csv",
        "target": "km_per_kwh",
        "unit": "km/kWh",
        "price_label": "Electricity price",
        "price_unit": "kWh",
        "fuels": {"electric": "Electricity"},
        "numeric": ["motors", "power_w", "voltage_v", "battery_kwh", "weight_kg", "max_speed_kph", "tire_in"],
        "categorical": ["brand"],
        "choices": {},
        "specs": [
            _spec("motors", "Motors", "", 1, 4, 1),
            _spec("power_w", "Motor power", "W", 100, 10000, 10),
            _spec("voltage_v", "Voltage", "V", 24, 120, 1),
            _spec("battery_kwh", "Battery size", "kWh", 0.1, 8, 0.01),
            _spec("weight_kg", "Weight", "kg", 5, 150, 0.1),
            _spec("max_speed_kph", "Top speed", "km/h", 15, 150, 1),
            _spec("tire_in", "Tyre size", "in", 6, 16, 0.5),
        ],
        "load_penalty": 0.08,
        "default": {"brand": "Xiaomi"},
    },
}

for _cat in CATEGORIES.values():
    _cat["features"] = _cat["numeric"] + _cat["categorical"]

# ----------------------------------------------------------- real-world adjustment
# The datasets list rated (brochure / test-cycle) mileage. The models predict that rated
# figure from the vehicle's specs. These multipliers turn it into a real-road estimate.
# They are documented assumptions, NOT learned from data - edit them here if you disagree.
ROAD_FACTOR = {"city": 0.88, "mixed": 1.00, "highway": 1.05}
SERVICE_OVERDUE_FACTOR = 0.95
AC_FACTOR = 0.92  # cars only
AGE_PENALTY_PER_YEAR = 0.005  # capped at 15 years
LOAD_UNIT_KG = 100

# Training data is petrol only for cars; other fuels scale the petrol km/l figure.
# Diesel engines go further per litre; CNG is measured in km per kg.
FUEL_FACTOR = {"petrol": 1.0, "diesel": 1.25, "cng": 1.35}
FUEL_UNIT = {"petrol": ("litre", "km/l"), "diesel": ("litre", "km/l"), "cng": ("kg", "km/kg"), "electric": ("kWh", "km/kWh")}


def real_world_factor(category: str, fuel: str, road: str, load_kg: float, ac_on: bool, overdue: bool, age: float) -> float:
    """Multiplier from rated mileage to estimated real-road mileage."""
    cfg = CATEGORIES[category]
    factor = ROAD_FACTOR[road]
    factor *= 1 - cfg["load_penalty"] * (load_kg / LOAD_UNIT_KG)
    factor *= 1 - AGE_PENALTY_PER_YEAR * min(age, 15)
    if overdue:
        factor *= SERVICE_OVERDUE_FACTOR
    if ac_on and category == "car":
        factor *= AC_FACTOR
    if category == "car":
        factor *= FUEL_FACTOR[fuel]
    return max(factor, 0.3)


FEATURE_NAMES = {
    "engine_cc": "Engine size",
    "power_ps": "Max power",
    "power_hp": "Max power",
    "torque_nm": "Max torque",
    "cylinders": "Cylinders",
    "gears": "Gears",
    "weight_kg": "Weight",
    "acceleration_s": "0-100 time",
    "motors": "Motors",
    "power_w": "Motor power",
    "voltage_v": "Voltage",
    "battery_kwh": "Battery size",
    "max_speed_kph": "Top speed",
    "tire_in": "Tyre size",
    "brand": "Brand",
    "category": "Bike or scooter",
    "cooling": "Cooling",
}

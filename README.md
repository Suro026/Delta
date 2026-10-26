# Delta: Know the difference

Delta is a Flask website that predicts a **bike, scooter, car or electric scooter's mileage** from real vehicle data, then turns it into the **cost of your trip** using the fuel price you type in. Every prediction shows the answer from **all six regression models** and **all six classification models** side by side.

## Run it (Windows)

```powershell
cd Student-Perfomance-Prediction
py -m pip install -r requirements.txt
py app.py
```

Open http://127.0.0.1:5000

The first run trains all 36 models (about a minute). After that it starts instantly.

To rebuild the data and retrain: `py build_dataset.py` then `py train.py`

## Pages

| Page | What it does |
|---|---|
| Home | Live demo: drag distance and fuel price, watch the odometer re-price a real prediction |
| Predict | Pick brand and model (specs fill in) or type your own, enter today's fuel price, see every model's result |
| Model results | Per vehicle type, 12 charts covering every model: R², error and training-time bars, actual-vs-predicted for each regressor, input importance (pick a model), classifier score bars and radar, and a confusion matrix for each classifier |
| History | Last 50 predictions |
| About | Problem, data sources, assumptions, limits |

## Data (all in `data/raw/`)

| File | Used for |
|---|---|
| `Bike_Features.csv` | Bikes and scooters (listed mileage, cc, power, torque, gears, cooling). Columns are shifted in many rows, so `build_dataset.py` finds each value by pattern. |
| `mpg_raw.csv` (same data as `auto-mpg.csv`) | Cars. Miles per gallon converted to km/l. |
| `Electric scooter - dataset.xlsx` | Electric scooters. Efficiency = range ÷ battery kWh. |
| `bike_sales_india.csv` | **Not used.** Looks randomly generated: engine size, fuel and mileage are unrelated to the model name. |
| `CAR DETAILS FROM CAR DEKHO.csv` | **Not used.** No mileage or engine columns. |

## The ML part

For each vehicle type:

1. **Regression** (Linear, Ridge, Decision Tree, KNN, Random Forest, Gradient Boosting) predicts mileage in km/l, or km/kWh.
2. **Classification** (Logistic Regression, Decision Tree, KNN, Random Forest, Gradient Boosting, SVM) predicts Thirsty / Balanced / Efficient (three equal-sized groups).

Pipeline: 80/20 split, median imputation, StandardScaler + OneHotEncoder, 5-fold cross-validation, permutation importance, confusion matrix. The best model is chosen by cross-validated score, because the electric scooter set has only 42 rows.

**Trip cost = distance ÷ real-road mileage × the fuel price you enter.**
Real-road mileage = predicted rated mileage × a multiplier for road type, load, vehicle age, AC and overdue service. Those multipliers are **assumptions, not learned from data**. They live in `features.py`.

## Limits to state in your report

- The car data is 1970–82 vehicles, so modern cars will usually beat the rated figure.
- Cars are trained on petrol only. Diesel (×1.25) and CNG (×1.35) are estimated scale factors.
- Bike mileage is the listed figure, not measured on a road.
- Electric scooters: 42 models and mostly kick-scooter style, so predictions are rough.
- Fuel prices are never fetched online. The user enters them.

## Files

```
app.py            Flask app, API, SQLite history, validation
features.py       Vehicle types, feature lists and the real-world multipliers
build_dataset.py  Cleans data/raw/* into data/bikes.csv, cars.csv, escoot.csv
train.py          Trains and compares the 36 models, writes models/metrics.json
templates/        HTML pages
static/           CSS, JS, bundled fonts and Chart.js (works offline)
models/           Saved models and metrics.json
```

"""
Step 5 — Fit Demand Forecasting Models (Prophet)
For each item, fit two variants:
  • Baseline          — Prophet with weekly seasonality only
  • Weather-augmented — Prophet + temp_avg + precipitation as extra regressors
"""
import pandas as pd
import numpy as np
import pickle
import logging
from pathlib import Path
from sklearn.metrics import mean_absolute_error, mean_squared_error
from prophet import Prophet

# Suppress verbose Stan/Prophet logging
logging.getLogger("prophet").setLevel(logging.WARNING)
logging.getLogger("cmdstanpy").setLevel(logging.WARNING)

Path("models").mkdir(exist_ok=True)
Path("output").mkdir(exist_ok=True)

# ── Load modeling table ───────────────────────────────────────────────────────
df = pd.read_csv("data/modeling_table.csv")
df["ds"] = pd.to_datetime(df["date"])

items = df["item_id"].unique()
results = []

PROPHET_KWARGS = dict(
    changepoint_prior_scale=0.05,
    seasonality_prior_scale=10.0,
    yearly_seasonality=False,
    weekly_seasonality=True,
    daily_seasonality=False,
)

for item_id in items:
    item_df = df[df["item_id"] == item_id].sort_values("ds").reset_index(drop=True)
    item_name = item_df["item_name"].iloc[0]

    print(f"\n── {item_name} ({item_id}) ── {len(item_df)} days ──────────────────────────")

    prophet_df = item_df[["ds", "daily_demand", "temp_avg", "precipitation"]].copy()
    prophet_df = prophet_df.rename(columns={"daily_demand": "y"})

    # ── Baseline model ────────────────────────────────────────────────────────
    baseline = Prophet(**PROPHET_KWARGS)
    baseline.fit(prophet_df[["ds", "y"]])

    # ── Weather-augmented model ───────────────────────────────────────────────
    weather_m = Prophet(**PROPHET_KWARGS)
    weather_m.add_regressor("temp_avg")
    weather_m.add_regressor("precipitation")
    weather_m.fit(prophet_df[["ds", "y", "temp_avg", "precipitation"]])

    # ── In-sample evaluation ──────────────────────────────────────────────────
    base_pred    = baseline.predict(prophet_df[["ds"]])
    weather_pred = weather_m.predict(prophet_df[["ds", "temp_avg", "precipitation"]])

    y_true = prophet_df["y"].values
    mae_b  = mean_absolute_error(y_true, base_pred["yhat"].values)
    rmse_b = np.sqrt(mean_squared_error(y_true, base_pred["yhat"].values))
    mae_w  = mean_absolute_error(y_true, weather_pred["yhat"].values)
    rmse_w = np.sqrt(mean_squared_error(y_true, weather_pred["yhat"].values))

    print(f"  Baseline  — MAE: {mae_b:6.2f}  RMSE: {rmse_b:6.2f}")
    print(f"  Weather   — MAE: {mae_w:6.2f}  RMSE: {rmse_w:6.2f}  "
          f"(Δ MAE = {mae_b - mae_w:+.2f})")

    # ── Persist models ────────────────────────────────────────────────────────
    with open(f"models/{item_id}_baseline.pkl", "wb") as fh:
        pickle.dump(baseline, fh)
    with open(f"models/{item_id}_weather.pkl", "wb") as fh:
        pickle.dump(weather_m, fh)

    results.append({
        "item_id":         item_id,
        "item_name":       item_name,
        "mae_baseline":    round(mae_b,  2),
        "rmse_baseline":   round(rmse_b, 2),
        "mae_weather":     round(mae_w,  2),
        "rmse_weather":    round(rmse_w, 2),
        "delta_mae":       round(mae_b - mae_w, 2),   # positive = weather helped
    })

# ── Summary table ─────────────────────────────────────────────────────────────
results_df = pd.DataFrame(results).sort_values("delta_mae", ascending=False)
print("\n\n══ Model Comparison Summary ═══════════════════════════════════════")
print(results_df.to_string(index=False))
print(f"\nItems where weather improves MAE : "
      f"{(results_df['delta_mae'] > 0).sum()} / {len(results_df)}")

results_df.to_csv("output/model_comparison.csv", index=False)
print("Saved → output/model_comparison.csv")
print("Models saved → models/")

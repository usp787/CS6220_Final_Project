"""
Step 6 — Generate Short-Horizon Demand Forecasts (14 days)
Load fitted Prophet models and produce daily demand forecasts for
2026-03-28 → 2026-04-10 for each item, using both model variants.
"""
import pandas as pd
import numpy as np
import pickle
from pathlib import Path

Path("output").mkdir(exist_ok=True)

# ── Load inputs ───────────────────────────────────────────────────────────────
weather  = pd.read_csv("data/weather.csv")
weather["ds"] = pd.to_datetime(weather["date"])

stock    = pd.read_csv("data/stock_snapshot.csv")

FCAST_START = pd.Timestamp("2026-03-28")
FCAST_END   = pd.Timestamp("2026-04-10")

fcast_weather = weather[
    (weather["ds"] >= FCAST_START) & (weather["ds"] <= FCAST_END)
].reset_index(drop=True)

print(f"Forecast window : {FCAST_START.date()} → {FCAST_END.date()} "
      f"({len(fcast_weather)} days)")

# ── Generate per-item forecasts ───────────────────────────────────────────────
models_dir = Path("models")
item_ids   = sorted({p.stem.split("_baseline")[0]
                     for p in models_dir.glob("*_baseline.pkl")})

all_rows = []

for item_id in item_ids:
    with open(f"models/{item_id}_baseline.pkl", "rb") as fh:
        baseline = pickle.load(fh)
    with open(f"models/{item_id}_weather.pkl", "rb") as fh:
        weather_m = pickle.load(fh)

    item_name = stock.loc[stock["item_id"] == item_id, "item_name"].iloc[0]

    # Baseline forecast (no weather regressors)
    base_pred = baseline.predict(fcast_weather[["ds"]])

    # Weather-augmented forecast
    w_pred = weather_m.predict(
        fcast_weather[["ds", "temp_avg", "precipitation"]]
    )

    for i in range(len(fcast_weather)):
        row = fcast_weather.iloc[i]
        all_rows.append({
            "item_id":           item_id,
            "item_name":         item_name,
            "date":              row["date"],
            "temp_avg":          row["temp_avg"],
            "precipitation":     row["precipitation"],
            "condition":         row["condition"],
            "forecast_baseline": max(0.0, round(float(base_pred.iloc[i]["yhat"]), 1)),
            "forecast_weather":  max(0.0, round(float(w_pred.iloc[i]["yhat"]),    1)),
        })

forecasts = pd.DataFrame(all_rows)

# ── Print per-item summary ────────────────────────────────────────────────────
print("\n══ 14-Day Average Daily Demand Forecast ════════════════════════════")
summary = (
    forecasts
    .groupby("item_name")[["forecast_baseline", "forecast_weather"]]
    .mean()
    .round(1)
    .reset_index()
    .sort_values("forecast_weather", ascending=False)
)
summary.columns = ["Item", "Avg/day (Baseline)", "Avg/day (Weather)"]
print(summary.to_string(index=False))

# ── Stock-out horizon (using weather forecast) ────────────────────────────────
print("\n══ Estimated Days Until Stock-Out (weather model) ══════════════════")
stockout_rows = []
for item_id in item_ids:
    item_name   = stock.loc[stock["item_id"] == item_id, "item_name"].iloc[0]
    cur_stock   = int(stock.loc[stock["item_id"] == item_id, "current_stock"].iloc[0])
    item_fcast  = forecasts[forecasts["item_id"] == item_id].sort_values("date")

    remaining = cur_stock
    days_out  = None
    for _, r in item_fcast.iterrows():
        remaining -= r["forecast_weather"]
        if remaining <= 0:
            days_out = (pd.Timestamp(r["date"]) - FCAST_START).days + 1
            break

    stockout_rows.append({
        "item_name":     item_name,
        "current_stock": cur_stock,
        "days_until_stockout": days_out if days_out else f">{len(item_fcast)}",
    })

stockout_df = pd.DataFrame(stockout_rows).sort_values(
    "days_until_stockout",
    key=lambda s: pd.to_numeric(s.astype(str).str.replace(">", ""), errors="coerce").fillna(999)
)
print(stockout_df.to_string(index=False))

# ── Save outputs ──────────────────────────────────────────────────────────────
forecasts.to_csv("output/demand_forecasts.csv", index=False)
stockout_df.to_csv("output/stockout_horizon.csv", index=False)
print("\nSaved → output/demand_forecasts.csv")
print("Saved → output/stockout_horizon.csv")

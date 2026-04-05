"""
Step 7 — Simulate Inventory Depletion and Estimate Stock-Out Days
Load demand forecasts (baseline and weather) plus the current stock snapshot.
Simulate daily depletion for each item and compute days-until-stock-out
for both model variants.

Outputs
-------
output/stockout_simulation.csv  – daily remaining stock per item (both models)
output/stockout_summary.csv     – days-until-stock-out summary (both models)
"""
import pandas as pd
from pathlib import Path

Path("output").mkdir(exist_ok=True)

# ── Load inputs ────────────────────────────────────────────────────────────────
forecasts = pd.read_csv("output/demand_forecasts.csv")
forecasts["date"] = pd.to_datetime(forecasts["date"])

stock = pd.read_csv("data/stock_snapshot.csv")
stock_map = dict(zip(stock["item_id"], stock["current_stock"]))

FCAST_START = forecasts["date"].min()
item_ids    = sorted(forecasts["item_id"].unique())

# ── Simulate daily depletion ───────────────────────────────────────────────────
sim_rows = []

for item_id in item_ids:
    item_fc   = forecasts[forecasts["item_id"] == item_id].sort_values("date").reset_index(drop=True)
    item_name = item_fc["item_name"].iloc[0]
    init_stock = stock_map[item_id]

    rem_base    = float(init_stock)
    rem_weather = float(init_stock)

    for _, row in item_fc.iterrows():
        rem_base    = max(0.0, rem_base    - row["forecast_baseline"])
        rem_weather = max(0.0, rem_weather - row["forecast_weather"])
        day_offset  = (row["date"] - FCAST_START).days + 1

        sim_rows.append({
            "item_id":             item_id,
            "item_name":           item_name,
            "date":                row["date"].date(),
            "day":                 day_offset,
            "forecast_baseline":   row["forecast_baseline"],
            "forecast_weather":    row["forecast_weather"],
            "remaining_baseline":  round(rem_base,    1),
            "remaining_weather":   round(rem_weather, 1),
        })

sim_df = pd.DataFrame(sim_rows)
sim_df.to_csv("output/stockout_simulation.csv", index=False)
print("Saved → output/stockout_simulation.csv")

# ── Compute days-until-stock-out for each item / model variant ─────────────────
summary_rows = []
HORIZON = int(forecasts.groupby("item_id")["date"].count().max())

for item_id in item_ids:
    item_name  = stock.loc[stock["item_id"] == item_id, "item_name"].iloc[0]
    cur_stock  = stock_map[item_id]
    item_sim   = sim_df[sim_df["item_id"] == item_id].sort_values("day")

    # Baseline: first day remaining stock hits 0
    base_zero = item_sim[item_sim["remaining_baseline"] <= 0]
    days_base = int(base_zero["day"].iloc[0]) if len(base_zero) else f">{HORIZON}"

    # Weather: first day remaining stock hits 0
    wthr_zero = item_sim[item_sim["remaining_weather"] <= 0]
    days_wthr = int(wthr_zero["day"].iloc[0]) if len(wthr_zero) else f">{HORIZON}"

    # Shift = weather days − baseline days (positive → weather predicts more runway)
    try:
        shift = int(days_wthr) - int(days_base)
    except (ValueError, TypeError):
        shift = "N/A"

    summary_rows.append({
        "item_id":                 item_id,
        "item_name":               item_name,
        "current_stock":           cur_stock,
        "days_until_stockout_base":    days_base,
        "days_until_stockout_weather": days_wthr,
        "stockout_day_shift":          shift,
    })

summary_df = pd.DataFrame(summary_rows)

# Sort by weather stock-out days ascending (soonest risk first)
summary_df_sorted = summary_df.sort_values(
    "days_until_stockout_weather",
    key=lambda s: pd.to_numeric(s.astype(str).str.replace(">", ""), errors="coerce").fillna(999)
)

summary_df_sorted.to_csv("output/stockout_summary.csv", index=False)

# ── Print ──────────────────────────────────────────────────────────────────────
print("\n══ Inventory Depletion Summary ══════════════════════════════════════")
print(f"{'Item':<14} {'Stock':>6}  {'Base days':>10}  {'Wthr days':>10}  {'Shift':>6}")
print("─" * 56)
for _, r in summary_df_sorted.iterrows():
    print(f"{r['item_name']:<14} {r['current_stock']:>6}  "
          f"{str(r['days_until_stockout_base']):>10}  "
          f"{str(r['days_until_stockout_weather']):>10}  "
          f"{str(r['stockout_day_shift']):>6}")

print("\nSaved → output/stockout_summary.csv")

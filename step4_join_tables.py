"""
Step 4 — Join Sales and Weather into Modeling Table
Merge the daily sales table and weather table on date.
Produce a modeling table with one row per item per day.
Target variable: daily_demand.  Features: weather predictors.
"""
import pandas as pd
import sqlite3

# ── Load sales from SQLite ────────────────────────────────────────────────────
conn = sqlite3.connect("data/inventory.db")
daily_sales = pd.read_sql("SELECT * FROM daily_sales", conn)
conn.close()
print(f"Loaded daily_sales  : {len(daily_sales):,} rows")

# ── Load weather CSV ──────────────────────────────────────────────────────────
weather = pd.read_csv("data/weather.csv")
print(f"Loaded weather      : {len(weather):,} rows")

# Keep only the historical window (sales dates) for the modeling table
hist_weather = weather[weather["date"] <= "2026-03-27"].copy()

# ── Left-join on date ─────────────────────────────────────────────────────────
modeling_table = daily_sales.merge(hist_weather, on="date", how="left")

print(f"\nModeling table      : {len(modeling_table):,} rows × {modeling_table.shape[1]} cols")
print(f"Date range          : {modeling_table['date'].min()} → {modeling_table['date'].max()}")
print(f"Items               : {modeling_table['item_name'].nunique()}")

# ── Null check ────────────────────────────────────────────────────────────────
nulls = modeling_table.isnull().sum()
missing = nulls[nulls > 0]
if missing.empty:
    print("No missing values after join.")
else:
    print(f"\nMissing values:\n{missing}")

# ── Sample ────────────────────────────────────────────────────────────────────
print("\nSample rows (modeling table):")
print(modeling_table.head(16).to_string(index=False))

# ── Correlation snapshot: demand vs. weather ──────────────────────────────────
print("\nCorrelation: daily_demand vs. weather features (all items pooled)")
corr = (
    modeling_table[["daily_demand", "temp_avg", "temp_min", "temp_max", "precipitation"]]
    .corr()["daily_demand"]
    .drop("daily_demand")
    .round(3)
)
print(corr.to_string())

# ── Save ──────────────────────────────────────────────────────────────────────
modeling_table.to_csv("data/modeling_table.csv", index=False)
print("\nSaved → data/modeling_table.csv")

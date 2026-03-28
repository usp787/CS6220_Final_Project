"""
Step 1 — Ingest Sales Data
Load past 3 months of item-level sales records from CSV files.
Aggregate raw transaction records to daily demand per item.
"""
import pandas as pd
import glob
import os
from pathlib import Path

Path("data").mkdir(exist_ok=True)

# ── Load all monthly sales CSVs ───────────────────────────────────────────────
csv_files = sorted(glob.glob("data/sales_*_2026.csv"))
if not csv_files:
    raise FileNotFoundError("No sales CSV files found in data/. Run generate_data.py first.")

frames = []
for f in csv_files:
    df = pd.read_csv(f, parse_dates=["date"])
    df["source_file"] = os.path.basename(f)
    frames.append(df)
    print(f"  Loaded {len(df):,} records from {os.path.basename(f)}")

raw_sales = pd.concat(frames, ignore_index=True)
print(f"\nTotal raw transactions: {len(raw_sales):,}")
print(f"Date range : {raw_sales['date'].min().date()} → {raw_sales['date'].max().date()}")
print(f"Unique items: {raw_sales['item_id'].nunique()}")
print("\nSample raw records:")
print(raw_sales.head(8).to_string(index=False))

# ── Aggregate to daily demand per item ───────────────────────────────────────
daily_demand = (
    raw_sales
    .groupby(["date", "item_id", "item_name"], as_index=False)["quantity"]
    .sum()
    .rename(columns={"quantity": "daily_demand"})
    .sort_values(["item_id", "date"])
    .reset_index(drop=True)
)

daily_demand["date"] = daily_demand["date"].dt.strftime("%Y-%m-%d")

print(f"\nAggregated to {len(daily_demand):,} item-day records")
print(f"(items × days = {daily_demand['item_id'].nunique()} × "
      f"{daily_demand['date'].nunique()} = "
      f"{daily_demand['item_id'].nunique() * daily_demand['date'].nunique()})")
print("\nSample aggregated records:")
print(daily_demand.head(16).to_string(index=False))

# ── Per-item summary ──────────────────────────────────────────────────────────
summary = (
    daily_demand
    .groupby("item_name")["daily_demand"]
    .agg(total="sum", avg_per_day="mean", min_day="min", max_day="max")
    .round(1)
    .sort_values("total", ascending=False)
    .reset_index()
)
print("\nPer-item demand summary:")
print(summary.to_string(index=False))

# ── Save ──────────────────────────────────────────────────────────────────────
daily_demand.to_csv("data/daily_demand.csv", index=False)
print("\nSaved → data/daily_demand.csv")

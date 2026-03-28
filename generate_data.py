"""
Generate synthetic coffee-shop sales data for the Retail Inventory Twin project.
Creates transaction-level CSV files (Jan–Mar 2026) and a stock snapshot.
"""
import pandas as pd
import numpy as np
from pathlib import Path

np.random.seed(42)
Path("data").mkdir(exist_ok=True)

# ── Items with base transactions/day and temperature sensitivity ──────────────
ITEMS = [
    {"item_id": "I001", "item_name": "Espresso",    "base_txn": 14, "weather_sensitivity": -0.9},
    {"item_id": "I002", "item_name": "Latte",        "base_txn": 20, "weather_sensitivity": -1.1},
    {"item_id": "I003", "item_name": "Cappuccino",   "base_txn": 13, "weather_sensitivity": -0.8},
    {"item_id": "I004", "item_name": "Americano",    "base_txn": 11, "weather_sensitivity": -0.5},
    {"item_id": "I005", "item_name": "Green Tea",    "base_txn":  8, "weather_sensitivity": -0.3},
    {"item_id": "I006", "item_name": "Muffin",       "base_txn":  9, "weather_sensitivity": -0.1},
    {"item_id": "I007", "item_name": "Croissant",    "base_txn": 11, "weather_sensitivity": -0.1},
    {"item_id": "I008", "item_name": "Sandwich",     "base_txn": 13, "weather_sensitivity":  0.2},
]

# ── Date range: 3 months of history ──────────────────────────────────────────
dates = pd.date_range("2026-01-01", "2026-03-27", freq="D")
n_days = len(dates)

# Boston-like temperature curve (Celsius): cold Jan, warming toward late Mar
day_idx = np.arange(n_days)
temp_avg = -5 + 18 * (day_idx / (n_days - 1)) + np.random.normal(0, 2.5, n_days)

# ── Generate transaction-level records ───────────────────────────────────────
records = []
txn_id = 1
for d_idx, date in enumerate(dates):
    is_weekend = date.dayofweek >= 5
    day_mult = 1.3 if is_weekend else 1.0
    t = temp_avg[d_idx]

    for item in ITEMS:
        # Warmer → fewer hot drinks; colder → more
        temp_effect = item["weather_sensitivity"] * (t - 5) / 10.0
        expected_txn = item["base_txn"] * day_mult * (1 - temp_effect)
        n_txn = max(1, int(expected_txn + np.random.normal(0, 2)))

        for _ in range(n_txn):
            qty = int(np.random.choice([1, 2, 3], p=[0.70, 0.22, 0.08]))
            records.append({
                "transaction_id": f"T{txn_id:07d}",
                "date": date.strftime("%Y-%m-%d"),
                "item_id": item["item_id"],
                "item_name": item["item_name"],
                "quantity": qty,
            })
            txn_id += 1

df = pd.DataFrame(records)
df["date_parsed"] = pd.to_datetime(df["date"])

# ── Save one CSV per month ────────────────────────────────────────────────────
for month, label in [(1, "jan"), (2, "feb"), (3, "mar")]:
    subset = df[df["date_parsed"].dt.month == month].drop(columns="date_parsed")
    path = f"data/sales_{label}_2026.csv"
    subset.to_csv(path, index=False)
    print(f"  Saved {len(subset):,} transaction records → {path}")

# ── Stock snapshot (current inventory as of 2026-03-28) ──────────────────────
np.random.seed(99)
stock_rows = []
for item in ITEMS:
    approx_daily_demand = item["base_txn"] * 1.5          # avg qty ~1.5
    current_stock = int(approx_daily_demand * np.random.uniform(5, 15))
    stock_rows.append({
        "item_id": item["item_id"],
        "item_name": item["item_name"],
        "current_stock": current_stock,
        "snapshot_date": "2026-03-28",
    })
stock_df = pd.DataFrame(stock_rows)
stock_df.to_csv("data/stock_snapshot.csv", index=False)
print(f"  Saved stock snapshot ({len(stock_df)} items) → data/stock_snapshot.csv")
print(f"\nTotal transactions generated: {len(df):,}")

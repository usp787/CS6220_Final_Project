"""
Step 2 — Store and Query Data Locally (SQLite)
Load cleaned sales and stock tables into a local SQLite database.
Demonstrate SQL-based cleaning, joining, and querying.
"""
import pandas as pd
import sqlite3
from pathlib import Path

DB_PATH = "data/inventory.db"
Path("data").mkdir(exist_ok=True)

# ── Load CSVs ─────────────────────────────────────────────────────────────────
daily_demand = pd.read_csv("data/daily_demand.csv")
stock_snapshot = pd.read_csv("data/stock_snapshot.csv")

# ── Write to SQLite ───────────────────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)
daily_demand.to_sql("daily_sales", conn, if_exists="replace", index=False)
stock_snapshot.to_sql("stock_snapshot", conn, if_exists="replace", index=False)
print(f"  daily_sales   : {len(daily_demand):,} rows loaded")
print(f"  stock_snapshot: {len(stock_snapshot)} rows loaded")
print(f"  Database      : {DB_PATH}")

# ── Query 1: Total sales by item ──────────────────────────────────────────────
print("\n── Total sales by item (SQL) ──────────────────────────────────────")
q1 = pd.read_sql("""
    SELECT item_name,
           SUM(daily_demand)            AS total_sold,
           ROUND(AVG(daily_demand), 1)  AS avg_per_day,
           COUNT(*)                     AS n_days
    FROM   daily_sales
    GROUP  BY item_name
    ORDER  BY total_sold DESC
""", conn)
print(q1.to_string(index=False))

# ── Query 2: Weekly demand trend (last 4 weeks) ───────────────────────────────
print("\n── Weekly demand trend — last 4 weeks (SQL) ──────────────────────")
q2 = pd.read_sql("""
    SELECT strftime('%Y-W%W', date)     AS week,
           SUM(daily_demand)            AS total_demand,
           ROUND(AVG(daily_demand), 1)  AS avg_daily_demand
    FROM   daily_sales
    WHERE  date >= date('2026-03-28', '-28 days')
    GROUP  BY week
    ORDER  BY week
""", conn)
print(q2.to_string(index=False))

# ── Query 3: Join — current stock vs. recent avg demand ──────────────────────
print("\n── Stock vs. recent avg demand (SQL join) ─────────────────────────")
q3 = pd.read_sql("""
    SELECT s.item_name,
           s.current_stock,
           ROUND(recent.avg_demand, 1)                          AS avg_daily_demand_14d,
           ROUND(s.current_stock * 1.0 / recent.avg_demand, 1) AS est_days_supply
    FROM   stock_snapshot s
    JOIN   (
               SELECT item_id,
                      AVG(daily_demand) AS avg_demand
               FROM   daily_sales
               WHERE  date >= date('2026-03-28', '-14 days')
               GROUP  BY item_id
           ) recent ON s.item_id = recent.item_id
    ORDER  BY est_days_supply ASC
""", conn)
print(q3.to_string(index=False))

conn.close()
print(f"\nDatabase saved → {DB_PATH}")

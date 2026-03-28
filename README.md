# Retail Inventory Twin

A lightweight digital model that combines recent sales history, current stock, and weather conditions to estimate when individual products are likely to run out.

**Author:** Jiarui Zha — zha.j@northeastern.edu, MSDS 2027

---

## Overview

This project builds a retail inventory twin for small retail settings (coffee shops, boutique stores) where both overstock and stock-outs are costly but data and computing resources are limited. The system predicts daily item demand and converts those forecasts into an interpretable **"days until stock-out"** metric, with a focus on showing how external drivers—especially temperature and precipitation—can improve inventory planning.

---

## Pipeline Steps

### Step 1 — Ingest Sales Data
**Tech stack:** `pandas`, CSV files

- Load the past three months of item-level sales records from CSV files.
- Aggregate raw transaction records to **daily demand per item**.

---

### Step 2 — Store and Query Data Locally
**Tech stack:** `SQLite`, `pandas`

- Load cleaned sales tables into a local SQLite database.
- SQLite is self-contained and serverless, making local deployment simple.
- Use SQL queries for cleaning, joining, and repeated querying across tables.

---

### Step 3 — Fetch Weather Data
**Tech stack:** `OpenWeather One Call API 3.0`, `requests` / `pandas`

- Pull historical and short-term forecast weather data aligned by date with the sales table.
- Features collected: daily temperature, precipitation, and basic weather conditions.
- OpenWeather One Call 3.0 provides 1,000 free API calls/day — sufficient for course-scale use.

---

### Step 4 — Join Sales and Weather into Modeling Table
**Tech stack:** `pandas`, `SQLite`

- Merge the sales table and weather table on date.
- Produce a modeling table with one row per item per day.
- Target variable: daily sales quantity. Features: weather-related predictors.

---

### Step 5 — Fit Demand Forecasting Models
**Tech stack:** `Prophet` (Meta/Facebook open-source), `Python`

- Fit a Prophet time-series model to daily demand for each item.
- Prophet handles trend and seasonality and supports additional regressors (weather variables).
- Train two variants per item:
  - **Baseline:** demand forecast with no weather regressors.
  - **Weather-augmented:** demand forecast with temperature and precipitation as extra regressors.

---

### Step 6 — Generate Short-Horizon Demand Forecasts
**Tech stack:** `Prophet`, `pandas`

- Produce short-term daily demand forecasts for each item.
- Results are framed as **short-term operational forecasts** (not long-range predictions) given the three-month history window.

---

### Step 7 — Simulate Inventory Depletion and Estimate Stock-Out Days
**Tech stack:** `pandas`, `Python`

- Combine per-item demand forecasts with the current stock snapshot.
- Simulate daily inventory depletion: `remaining stock = current stock − cumulative forecasted demand`.
- Compute **days until stock-out** for each item.

---

### Step 8 — Evaluate and Compare Models
**Tech stack:** `Prophet diagnostics`, `scikit-learn` (metrics), `pandas`

- Compare baseline vs. weather-augmented forecasts on forecast error metrics (MAE, RMSE).
- Evaluate stock-out usefulness: does weather augmentation produce better-timed stock-out alerts?
- Identify which items benefit from external weather regressors and which do not.

---

### Step 9 — Report At-Risk Items
**Tech stack:** `pandas`, `matplotlib` / `seaborn`

- Rank items by days until stock-out (ascending).
- Surface which items are at **greatest risk of stocking out first** and on what approximate timeline.
- Visualize demand forecasts, inventory depletion curves, and stock-out risk rankings.

---

## Data Sources

| Source | Description |
|--------|-------------|
| Sales CSV files | Past 3 months of item-level sales records |
| Current stock snapshot | Per-item on-hand inventory counts |
| OpenWeather One Call 3.0 | Daily temperature, precipitation, weather conditions |

---

## References

1. SQLite. "About SQLite." sqlite.org/about.html
2. OpenWeather. "Pricing / One Call API 3.0." openweathermap.org/price
3. Prophet Documentation. "Seasonality, Holiday Effects, and Regressors"; "Diagnostics." facebook.github.io/prophet/

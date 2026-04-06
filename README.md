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



## Update (2026-04-02)

- Three months of sales and weather data is insufficient for Prophet to learn meaningful seasonal patterns; a longer historical window is required.
- A RAG-based or similar retrieval mechanism should be explored to handle demand forecasting for **unforeseen or new products** with no sales history.
- Various input/output pipelines need to be established for real deployment scenarios. Current thinking: CSV file as input, text-only forecasting report as output. Additional formats (structured JSON, dashboard integration) remain under consideration as a bonus.

---

## Update (2026-04-06)

### Extended Training Data: Jan 2024 – Mar 2026 (~27 months)

The training window was expanded from 3 months (Jan–Mar 2026) to 27 months (Jan 2024 – Mar 2026) using extended synthetic data, addressing the data-insufficiency concern noted on 2026-04-02.

**What changed in the pipeline:**

- **`generate_data.py`** — Date range extended to `2024-01-01`. The linear temperature ramp was replaced with an **annual sinusoidal cycle** (`10 − 13·cos(2π·doy/365)`), producing realistic Boston winters (~−3 °C) and summers (~23 °C) across multiple years. Monthly CSV output is now fully dynamic, generating one file per month-year combination (27 files total: `sales_jan_2024.csv` → `sales_mar_2026.csv`).
- **`step1_ingest_sales.py`** — Glob pattern broadened from `sales_*_2026.csv` to `sales_*.csv` to automatically pick up all years.
- **`step3_fetch_weather.py`** — `HIST_START` moved to `2024-01-01`. The synthetic weather generator was updated with the same sinusoidal temperature model, ensuring weather and sales share a consistent seasonal signal across the full 27-month span.
- **`step5_fit_models.py`** — `yearly_seasonality` enabled (`True`); `seasonality_mode` switched to `"multiplicative"`, which better captures demand that scales proportionally with season rather than shifting by a fixed offset.

**No API cost incurred** — all extended data uses the existing synthetic fallback path; the OpenWeather API path is unchanged.

**Model performance notes:**

- Raw MAE/RMSE values are higher in the 27-month model than in the 3-month model, but this is expected: the wider temperature range (full annual cycle vs. a narrow Jan–Mar ramp) increases demand variance, which mechanically raises absolute error.
- The **weather benefit (ΔMAE)** is preserved across all items and improves for Espresso (+1.50 vs. +0.82 previously), confirming the model extracts more temperature signal from the richer dataset.
- The 27-month model captures the **summer demand trough** for hot drinks — a seasonal pattern the 3-month model was structurally blind to.
- Stock-out timing predictions are more conservative and operationally stable compared to the 3-month model, which produced overly optimistic stock-life estimates driven by a narrow rising-temperature window.

---

## Future Plan (2026-04-06)

### Part 1 — Web Frontend (FastAPI + HTML)

**Step 1 — FastAPI backend**

Create a `app.py` entry point with three endpoints:

- `POST /validate` — accepts uploaded CSV files, passes them through the RAG validation layer (Part 2), and returns a validation result (accepted / rejected / warnings) before any forecasting begins.
- `POST /forecast` — accepts validated CSV files, triggers steps 1–9 as a background task, and returns the text content of `stockout_report.txt` when complete.
- `GET /report` — returns the most recently generated `stockout_report.txt` as plain text.

Steps 1–9 are rewired from standalone scripts into importable functions called by the backend. No other logic in the core pipeline changes.

**Step 2 — HTML frontend**

A single static HTML page (`index.html`) served by FastAPI's `StaticFiles` mount:

- A file picker restricted to `.csv` for sales data, and a second picker for the stock snapshot CSV.
- A submit button that calls `/validate` first; on acceptance, calls `/forecast`.
- A read-only text area that displays the returned `stockout_report.txt` content in the browser.
- Plain `fetch` API calls only — no JavaScript framework.

JSON input and plot output are deferred as optional extras.

---

### Part 2 — RAG Input Validation Layer

The RAG layer runs between upload and step 1 to reject or flag data that is outside the model's training domain or structurally incompatible with the expected schema.

#### Vector Database Content

The vector store holds three categories of short text documents:

1. **Known item profiles** — one document per trained item (I001–I008), describing item name, category (hot drink / cold drink / food), typical daily demand range, and seasonal behavior (e.g., `"Espresso — hot drink — demand peaks in winter, 20–35 units/day"`).
2. **Schema definition** — expected CSV structure: required columns (`transaction_id`, `date`, `item_id`, `item_name`, `quantity`), date format, and value constraints.
3. **Domain boundary examples** — short descriptions of out-of-scope data: non-food retail (auto parts, electronics), non-transactional formats (sensor logs, financial ledgers), and item categories absent from the trained set.

Total document count: ~20–30 chunks. `chromadb` or `faiss` as an in-process vector store is sufficient; no hosted vector database is needed at this scale.

#### Embedding Model

`sentence-transformers/all-MiniLM-L6-v2` (22 M parameters, 384-dimensional output). Inputs are short texts — CSV column headers and a few sampled rows rendered as natural language — so a compact model is appropriate. Runs on CPU with negligible latency.



#### Validation Logic Flow

1. Parse the uploaded CSV header and sample 3–5 rows.
2. Render as a short natural-language string (e.g., `"columns: date, item_id, item_name, qty — items: latte, espresso, muffin"`).
3. Embed with `all-MiniLM-L6-v2` and query the vector store for top-3 documents with similarity scores.
4. **Pass** if top similarity ≥ 0.60 and all required columns are present.
5. **Warn** if similarity is 0.35–0.60 or a required column is missing — pipeline proceeds with a caution message.
6. **Reject** if top similarity < 0.35 — block the pipline and return
the error message to user and ask valid input.
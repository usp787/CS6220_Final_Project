"""
app.py — FastAPI backend for the Retail Inventory Twin web frontend.

Endpoints
---------
GET  /                  Serve the HTML frontend (index.html)
POST /validate          Schema-validate uploaded CSV files before forecasting
POST /forecast          Save files, run pipeline, return stockout_report.txt
GET  /report            Return the most recent stockout_report.txt

Start the server
----------------
    uvicorn app:app --reload --host 0.0.0.0 --port 8000

Then open http://localhost:8000 in your browser.
"""

import io
from pathlib import Path
from typing import List

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from pipeline import BASE_DIR, run_pipeline

# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Retail Inventory Twin",
    description="Upload sales + stock CSVs and get a stock-out forecast report.",
    version="1.0.0",
)

STATIC_DIR = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── Expected CSV schemas ──────────────────────────────────────────────────────
SALES_REQUIRED = {"transaction_id", "date", "item_id", "item_name", "quantity"}
STOCK_REQUIRED = {"item_id", "item_name", "current_stock"}


# ── Helpers ───────────────────────────────────────────────────────────────────
def _check_schema(content: bytes, required: set, label: str) -> dict:
    """
    Parse a CSV from bytes and verify required columns are present.
    Returns a dict with keys: status ('accepted'/'rejected'), message, rows.
    """
    try:
        df = pd.read_csv(io.BytesIO(content), nrows=5)
    except Exception as exc:
        return {"status": "rejected", "message": f"Cannot parse {label}: {exc}", "rows": 0}

    missing = required - set(df.columns)
    if missing:
        return {
            "status": "rejected",
            "message": f"{label}: missing required columns {sorted(missing)}",
            "rows": 0,
        }

    # Count rows without re-reading the whole file
    try:
        total_rows = sum(1 for _ in io.BytesIO(content)) - 1  # subtract header
    except Exception:
        total_rows = -1

    return {"status": "accepted", "message": f"{label}: schema OK", "rows": total_rows}


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the HTML frontend."""
    html_path = STATIC_DIR / "index.html"
    return html_path.read_text(encoding="utf-8")


@app.post("/validate")
async def validate(
    sales_files: List[UploadFile] = File(..., description="One or more sales_*.csv files"),
    stock_file: UploadFile = File(..., description="stock_snapshot.csv"),
):
    """
    Validate uploaded CSV files against expected schemas.

    Returns
    -------
    {
        "status": "accepted" | "warning" | "rejected",
        "message": "...",
        "warnings": [...],
        "files": [{ "status", "message", "rows" }, ...]
    }
    """
    file_results = []
    warnings: List[str] = []

    # --- Validate each sales file ---
    for upload in sales_files:
        content = await upload.read()
        result = _check_schema(content, SALES_REQUIRED, upload.filename or "sales file")
        if result["status"] == "rejected":
            return JSONResponse(
                status_code=422,
                content={"status": "rejected", "message": result["message"], "warnings": [], "files": []},
            )
        file_results.append({"filename": upload.filename, **result})

        # Naming convention check (non-blocking warning)
        fname = upload.filename or ""
        if not (fname.startswith("sales_") and fname.endswith(".csv")):
            warnings.append(
                f"'{fname}' does not follow the expected naming pattern (sales_*.csv). "
                "Ensure it matches the glob pattern used by step 1."
            )

    # --- Validate stock snapshot ---
    stock_content = await stock_file.read()
    stock_result = _check_schema(stock_content, STOCK_REQUIRED, stock_file.filename or "stock file")
    if stock_result["status"] == "rejected":
        return JSONResponse(
            status_code=422,
            content={"status": "rejected", "message": stock_result["message"], "warnings": [], "files": []},
        )
    file_results.append({"filename": stock_file.filename, **stock_result})

    overall = "warning" if warnings else "accepted"
    return {
        "status": overall,
        "message": "All files passed schema validation.",
        "warnings": warnings,
        "files": file_results,
    }


@app.post("/forecast")
async def forecast(
    sales_files: List[UploadFile] = File(..., description="One or more sales_*.csv files"),
    stock_file: UploadFile = File(..., description="stock_snapshot.csv"),
    retrain: bool = Query(False, description="Force retraining of Prophet models (slow ~5 min)"),
):
    """
    Save uploaded files to data/, run the full pipeline (steps 1–9), and
    return the text of output/stockout_report.txt.

    Step 5 (model fitting) is skipped when retrain=false and trained models
    already exist, keeping typical response time under 30 seconds.
    """
    data_dir = BASE_DIR / "data"
    data_dir.mkdir(exist_ok=True)

    # Save sales files — preserve original filenames so glob in step1 picks them up
    for upload in sales_files:
        content = await upload.read()
        fname = upload.filename or "sales_upload.csv"
        (data_dir / fname).write_bytes(content)

    # Save stock snapshot under the fixed name expected by step2 and step6
    stock_content = await stock_file.read()
    (data_dir / "stock_snapshot.csv").write_bytes(stock_content)

    try:
        report_text = run_pipeline(retrain=retrain)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {"status": "success", "report": report_text}


@app.get("/report", response_class=PlainTextResponse)
async def get_report():
    """Return the most recently generated stockout_report.txt as plain text."""
    report_path = BASE_DIR / "output" / "stockout_report.txt"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="No report has been generated yet. Run /forecast first.")
    return report_path.read_text(encoding="utf-8")

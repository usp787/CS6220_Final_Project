"""
app.py — FastAPI backend for the Retail Inventory Twin web frontend.

Endpoints
---------
GET  /                  Serve the HTML frontend (index.html)
POST /validate          Schema + RAG domain validation before forecasting
POST /forecast          Save files, run pipeline, return stockout_report.txt
GET  /report            Return the most recent stockout_report.txt

Validation pipeline (POST /validate)
-------------------------------------
  1. Schema gate  — checks required columns in each CSV (fast, no model needed).
                    Immediate rejection if columns are missing.
  2. RAG check    — embeds a natural-language summary of each sales CSV with
                    all-MiniLM-L6-v2 and queries a ChromaDB vector store of
                    ~20 domain documents (item profiles, schema specs, boundary
                    examples).  Cosine similarity against valid-domain docs:
                      ≥ 0.60  → accepted
                      0.35–0.59 → warning (pipeline proceeds with caution)
                      < 0.35  → rejected (pipeline blocked)

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
from rag_validator import validate_sales_csv

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
    Fast schema gate: parse the CSV and verify required columns exist.
    Returns dict with keys: status ('accepted'/'rejected'), message, rows.
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

    try:
        total_rows = sum(1 for _ in io.BytesIO(content)) - 1   # subtract header
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
    Two-stage validation: schema check → RAG domain check.

    Returns
    -------
    {
        "status":   "accepted" | "warning" | "rejected",
        "message":  "...",
        "warnings": [...],
        "files": [
            {
                "filename":   "...",
                "status":     "accepted"|"warning"|"rejected",
                "message":    "...",
                "rows":       int,
                "similarity": float,       # RAG cosine score (-1 if unavailable)
                "rag_details": [...]        # top-3 matching documents
            },
            ...
        ]
    }
    """
    file_results: List[dict] = []
    warnings:     List[str]  = []
    overall_rejected = False

    # ── Validate each sales file ──────────────────────────────────────────────
    for upload in sales_files:
        content = await upload.read()
        fname   = upload.filename or "sales_file.csv"

        # Stage 1: schema gate
        schema_result = _check_schema(content, SALES_REQUIRED, fname)
        if schema_result["status"] == "rejected":
            return JSONResponse(
                status_code=422,
                content={
                    "status":   "rejected",
                    "message":  schema_result["message"],
                    "warnings": [],
                    "files":    [],
                },
            )

        # Stage 2: RAG domain check
        rag_result = validate_sales_csv(content, filename=fname)

        entry = {
            "filename":    fname,
            "status":      rag_result["status"],
            "message":     rag_result["message"],
            "rows":        schema_result["rows"],
            "similarity":  rag_result["similarity"],
            "rag_details": rag_result["details"],
        }
        file_results.append(entry)

        if rag_result["status"] == "rejected":
            overall_rejected = True
        elif rag_result["status"] == "warning":
            warnings.append(f"{fname}: {rag_result['message']}")

        # Naming convention check (non-blocking warning)
        if not (fname.startswith("sales_") and fname.endswith(".csv")):
            warnings.append(
                f"'{fname}' does not follow the expected naming pattern (sales_*.csv). "
                "Ensure it matches the glob pattern used by step 1."
            )

    # ── Validate stock snapshot (schema only — no RAG) ────────────────────────
    stock_content = await stock_file.read()
    stock_schema  = _check_schema(stock_content, STOCK_REQUIRED, stock_file.filename or "stock file")
    if stock_schema["status"] == "rejected":
        return JSONResponse(
            status_code=422,
            content={
                "status":   "rejected",
                "message":  stock_schema["message"],
                "warnings": [],
                "files":    [],
            },
        )
    file_results.append({
        "filename":    stock_file.filename,
        "status":      "accepted",
        "message":     stock_schema["message"],
        "rows":        stock_schema["rows"],
        "similarity":  None,
        "rag_details": [],
    })

    # ── Aggregate decision ────────────────────────────────────────────────────
    if overall_rejected:
        # Surface the first rejection reason as the top-level message
        rejected_entry = next(f for f in file_results if f["status"] == "rejected")
        return JSONResponse(
            status_code=422,
            content={
                "status":   "rejected",
                "message":  rejected_entry["message"],
                "warnings": warnings,
                "files":    file_results,
            },
        )

    overall_status  = "warning" if warnings else "accepted"
    overall_message = (
        "All files passed validation."
        if overall_status == "accepted"
        else f"{len(warnings)} warning(s) — review before proceeding."
    )
    return {
        "status":   overall_status,
        "message":  overall_message,
        "warnings": warnings,
        "files":    file_results,
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

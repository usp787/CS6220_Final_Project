"""
pipeline.py — Orchestrates steps 1–9 of the Retail Inventory Twin pipeline.

Each step is executed as an isolated subprocess so existing scripts need no
modification.  Steps are run from the project root so all relative data paths
(data/, models/, output/) resolve correctly.

Usage
-----
    from pipeline import run_pipeline, models_exist

    report_text = run_pipeline(retrain=False)   # skips step5 if models exist
    report_text = run_pipeline(retrain=True)    # always runs step5
"""

import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()

# Ordered list of (script_filename, human-readable description)
STEPS = [
    ("step1_ingest_sales.py",  "Step 1 — Ingesting sales data"),
    ("step2_sqlite_store.py",  "Step 2 — Storing data to SQLite"),
    ("step3_fetch_weather.py", "Step 3 — Generating weather data"),
    ("step4_join_tables.py",   "Step 4 — Joining sales and weather"),
    ("step5_fit_models.py",    "Step 5 — Fitting Prophet models (may take several minutes)"),
    ("step6_forecast.py",      "Step 6 — Generating 14-day forecasts"),
    ("step7_stockout_sim.py",  "Step 7 — Simulating inventory depletion"),
    ("step8_evaluate.py",      "Step 8 — Evaluating model accuracy"),
    ("step9_report.py",        "Step 9 — Generating at-risk report"),
]


def models_exist() -> bool:
    """Return True if all 8 baseline Prophet model pickles are present."""
    existing = list((BASE_DIR / "models").glob("*_baseline.pkl"))
    return len(existing) >= 8


def _run_step(script_name: str, description: str) -> str:
    """
    Execute a single pipeline step in a subprocess.
    Returns combined stdout+stderr on success.
    Raises RuntimeError on non-zero exit.
    """
    print(f"  {description}...", flush=True)
    # Force UTF-8 stdout/stderr inside the subprocess so Unicode characters
    # (Δ, −, etc.) in step outputs don't crash on Windows GBK terminals.
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, script_name],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,          # 10-minute cap per step
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{script_name} exited with code {result.returncode}.\n"
            f"--- stderr ---\n{result.stderr}\n"
            f"--- stdout ---\n{result.stdout}"
        )
    return result.stdout + result.stderr


def run_pipeline(retrain: bool = False) -> str:
    """
    Run the full pipeline and return the contents of
    output/stockout_report.txt as a string.

    Parameters
    ----------
    retrain : bool
        If False (default) and models already exist, step 5 (model fitting)
        is skipped to keep the endpoint fast.  Set True to force retraining.
    """
    skip_step5 = (not retrain) and models_exist()

    print("[pipeline] Starting Retail Inventory Twin pipeline...", flush=True)
    for script, desc in STEPS:
        if skip_step5 and script == "step5_fit_models.py":
            print(f"  {desc} — SKIPPED (existing models found)", flush=True)
            continue
        _run_step(script, desc)

    report_path = BASE_DIR / "output" / "stockout_report.txt"
    if not report_path.exists():
        raise RuntimeError("Pipeline finished but stockout_report.txt was not produced.")

    print("[pipeline] Done.", flush=True)
    return report_path.read_text(encoding="utf-8")

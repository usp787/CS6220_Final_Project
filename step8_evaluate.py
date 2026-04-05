"""
Step 8 — Evaluate and Compare Models
Combines in-sample forecast metrics (MAE, RMSE) from Step 5 with the
stock-out timing produced in Step 7 to answer:
  1. Which items benefit from weather regressors?
  2. Does weather augmentation shift stock-out alert timing meaningfully?

Outputs
-------
output/evaluation_report.txt  – human-readable evaluation summary
"""
import pandas as pd
from pathlib import Path

Path("output").mkdir(exist_ok=True)

# ── Load inputs ────────────────────────────────────────────────────────────────
metrics  = pd.read_csv("output/model_comparison.csv")   # from step 5
summary  = pd.read_csv("output/stockout_summary.csv")   # from step 7

eval_df = metrics.merge(
    summary[["item_id", "current_stock",
             "days_until_stockout_base", "days_until_stockout_weather",
             "stockout_day_shift"]],
    on="item_id",
    how="left",
)

# ── Classify weather benefit ───────────────────────────────────────────────────
DELTA_THRESHOLD = 0.5   # MAE improvement threshold (units = daily sales)

eval_df["weather_helps_forecast"] = eval_df["delta_mae"].apply(
    lambda d: "Yes" if d > DELTA_THRESHOLD else ("Marginal" if d > 0 else "No")
)

# ── Build text report ──────────────────────────────────────────────────────────
lines = []

lines.append("=" * 68)
lines.append("  Retail Inventory Twin — Model Evaluation Report")
lines.append("=" * 68)

# 1. Forecast accuracy comparison
lines.append("\n1. FORECAST ACCURACY (in-sample MAE / RMSE)")
lines.append("-" * 68)
header = f"{'Item':<14} {'MAE Base':>9} {'MAE Wthr':>9} {'ΔMAE':>7} {'RMSE Base':>10} {'RMSE Wthr':>10}"
lines.append(header)
lines.append("-" * 68)
for _, r in metrics.sort_values("delta_mae", ascending=False).iterrows():
    lines.append(
        f"{r['item_name']:<14} {r['mae_baseline']:>9.2f} {r['mae_weather']:>9.2f} "
        f"{r['delta_mae']:>+7.2f} {r['rmse_baseline']:>10.2f} {r['rmse_weather']:>10.2f}"
    )
lines.append("-" * 68)
n_helps  = (metrics["delta_mae"] > DELTA_THRESHOLD).sum()
n_marg   = ((metrics["delta_mae"] > 0) & (metrics["delta_mae"] <= DELTA_THRESHOLD)).sum()
n_no     = (metrics["delta_mae"] <= 0).sum()
lines.append(f"  Weather clearly improves MAE (>{DELTA_THRESHOLD}): {n_helps}/{len(metrics)} items")
lines.append(f"  Marginal improvement (0–{DELTA_THRESHOLD}):          {n_marg}/{len(metrics)} items")
lines.append(f"  No improvement / worse:                {n_no}/{len(metrics)} items")

# 2. Stock-out timing comparison
lines.append("\n2. STOCK-OUT TIMING SHIFT  (weather days − baseline days)")
lines.append("-" * 68)
lines.append(
    f"{'Item':<14} {'Stock':>6}  {'Base days':>10}  {'Wthr days':>10}  "
    f"{'Shift':>7}  {'Wthr helps?':>12}"
)
lines.append("-" * 68)

for _, r in eval_df.sort_values(
    "days_until_stockout_weather",
    key=lambda s: pd.to_numeric(s.astype(str).str.replace(">", ""), errors="coerce").fillna(999)
).iterrows():
    shift_str = str(r["stockout_day_shift"])
    lines.append(
        f"{r['item_name']:<14} {r['current_stock']:>6}  "
        f"{str(r['days_until_stockout_base']):>10}  "
        f"{str(r['days_until_stockout_weather']):>10}  "
        f"{shift_str:>7}  {r['weather_helps_forecast']:>12}"
    )

# 3. Key findings
lines.append("\n3. KEY FINDINGS")
lines.append("-" * 68)

# Items with most MAE improvement
top_item = metrics.sort_values("delta_mae", ascending=False).iloc[0]
lines.append(
    f"  • Largest MAE improvement: {top_item['item_name']} "
    f"(ΔMAE = {top_item['delta_mae']:+.2f})"
)

# Items where weather shifts stock-out alert
numeric_shift = pd.to_numeric(
    eval_df["stockout_day_shift"].astype(str), errors="coerce"
)
shifted = eval_df[numeric_shift.abs() >= 1]
if len(shifted):
    examples = ", ".join(
        f"{r['item_name']} ({int(r['stockout_day_shift']):+d}d)"
        for _, r in shifted.sort_values(
            "stockout_day_shift",
            key=lambda s: pd.to_numeric(s.astype(str), errors="coerce").abs(),
            ascending=False
        ).iterrows()
        if pd.notna(pd.to_numeric(r["stockout_day_shift"], errors="coerce"))
    )
    lines.append(f"  • Stock-out timing shifted ≥1 day: {examples}")
else:
    lines.append("  • Stock-out timing shift < 1 day for all items within the 14-day window.")

# Items that do NOT benefit
no_help = eval_df[eval_df["weather_helps_forecast"] == "No"]["item_name"].tolist()
if no_help:
    lines.append(
        f"  • Items with no weather benefit: {', '.join(no_help)} "
        f"— baseline model sufficient for these."
    )

lines.append("\n" + "=" * 68)

report_text = "\n".join(lines)
print(report_text)

report_path = Path("output/evaluation_report.txt")
report_path.write_text(report_text, encoding="utf-8")
print(f"\nSaved → {report_path}")

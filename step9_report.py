"""
Step 9 — Report At-Risk Items
Rank items by days-until-stock-out and surface the greatest risks.
Primary output: plain-text operational report.
Bonus output:   three matplotlib figures saved to output/figures/.

Figures
-------
  fig1_stockout_risk.png   – bar chart: days until stock-out (weather model)
  fig2_depletion_curves.png – line chart: daily remaining stock per item
  fig3_model_comparison.png – bar chart: MAE improvement from weather
"""
import pandas as pd
import matplotlib
matplotlib.use("Agg")           # headless — no display required
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from pathlib import Path

Path("output/figures").mkdir(parents=True, exist_ok=True)

# ── Load inputs ────────────────────────────────────────────────────────────────
summary   = pd.read_csv("output/stockout_summary.csv")
sim_df    = pd.read_csv("output/stockout_simulation.csv", parse_dates=["date"])
metrics   = pd.read_csv("output/model_comparison.csv")
forecasts = pd.read_csv("output/demand_forecasts.csv", parse_dates=["date"])

HORIZON     = int(forecasts.groupby("item_id")["date"].count().max())
FCAST_START = forecasts["date"].min()
FCAST_END   = forecasts["date"].max()

# ── Helpers ────────────────────────────────────────────────────────────────────
def _to_numeric_days(val):
    """Convert '>14' style strings to a float (999 for 'no stock-out')."""
    s = str(val)
    if s.startswith(">"):
        return float("inf")
    try:
        return float(s)
    except ValueError:
        return float("inf")


def _fmt_days(val):
    d = _to_numeric_days(val)
    return f">{HORIZON}" if d == float("inf") else str(int(d))


# ── Sort by risk (soonest stock-out first) ─────────────────────────────────────
summary_sorted = summary.copy()
summary_sorted["_sort_key"] = summary_sorted["days_until_stockout_weather"].apply(_to_numeric_days)
summary_sorted = summary_sorted.sort_values("_sort_key").reset_index(drop=True)

# ── Text report ────────────────────────────────────────────────────────────────
lines = []
lines.append("=" * 68)
lines.append("  Retail Inventory Twin — At-Risk Stock-Out Report")
lines.append(f"  Forecast window: {FCAST_START.date()} → {FCAST_END.date()} "
             f"({HORIZON} days)")
lines.append("=" * 68)

lines.append("\nSTOCK-OUT RISK RANKING  (weather-augmented model, soonest first)")
lines.append("-" * 68)
lines.append(f"  {'#':<3} {'Item':<14} {'On-hand':>8}  {'Days left':>10}  {'Status'}")
lines.append("-" * 68)

ALERT_DAYS  = 5
CAUTION_DAYS = 10

for rank, (_, r) in enumerate(summary_sorted.iterrows(), 1):
    d = _to_numeric_days(r["days_until_stockout_weather"])
    if d <= ALERT_DAYS:
        status = "** ALERT **"
    elif d <= CAUTION_DAYS:
        status = "* Caution *"
    else:
        status = "  OK"

    lines.append(
        f"  {rank:<3} {r['item_name']:<14} {r['current_stock']:>8}  "
        f"{_fmt_days(r['days_until_stockout_weather']):>10}  {status}"
    )

lines.append("-" * 68)

# Alert / caution items narrative
alert_items   = summary_sorted[summary_sorted["_sort_key"] <= ALERT_DAYS]
caution_items = summary_sorted[
    (summary_sorted["_sort_key"] > ALERT_DAYS) &
    (summary_sorted["_sort_key"] <= CAUTION_DAYS)
]

lines.append("\nSUMMARY")
lines.append("-" * 68)
if len(alert_items):
    names = ", ".join(alert_items["item_name"].tolist())
    lines.append(f"  ALERT   (≤{ALERT_DAYS} days):   {names}")
    lines.append(f"          → Reorder immediately to avoid stock-out.")
if len(caution_items):
    names = ", ".join(caution_items["item_name"].tolist())
    lines.append(f"  Caution ({ALERT_DAYS+1}–{CAUTION_DAYS} days): {names}")
    lines.append(f"          → Schedule reorder within the next few days.")
safe_items = summary_sorted[summary_sorted["_sort_key"] > CAUTION_DAYS]
if len(safe_items):
    names = ", ".join(safe_items["item_name"].tolist())
    lines.append(f"  OK      (>{CAUTION_DAYS} days):  {names}")

lines.append("\nFORECAST DETAIL  (avg daily demand, weather model)")
lines.append("-" * 68)
avg_demand = (
    forecasts.groupby(["item_id", "item_name"])["forecast_weather"]
    .mean()
    .reset_index()
    .rename(columns={"forecast_weather": "avg_daily"})
)
avg_demand = avg_demand.merge(
    summary_sorted[["item_id", "days_until_stockout_weather", "_sort_key"]],
    on="item_id"
).sort_values("_sort_key")

lines.append(f"  {'Item':<14}  {'Avg demand/day':>15}  {'Days until stock-out':>20}")
lines.append(f"  {'-'*14}  {'-'*15}  {'-'*20}")
for _, r in avg_demand.iterrows():
    lines.append(
        f"  {r['item_name']:<14}  {r['avg_daily']:>15.1f}  "
        f"{_fmt_days(r['days_until_stockout_weather']):>20}"
    )

lines.append("\n" + "=" * 68)
lines.append("  Figures saved to output/figures/")
lines.append("=" * 68)

report_text = "\n".join(lines)
print(report_text)

report_path = Path("output/stockout_report.txt")
report_path.write_text(report_text, encoding="utf-8")
print(f"\nSaved → {report_path}")

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE 1 — Stock-Out Risk Ranking
# ══════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(9, 5))

items_plot = summary_sorted["item_name"].tolist()
days_base  = [min(_to_numeric_days(v), HORIZON + 1) for v in summary_sorted["days_until_stockout_base"]]
days_wthr  = [min(_to_numeric_days(v), HORIZON + 1) for v in summary_sorted["days_until_stockout_weather"]]

x = range(len(items_plot))
width = 0.35

bars_b = ax.bar([i - width/2 for i in x], days_base, width,
                label="Baseline", color="#7BA7BC", alpha=0.85)
bars_w = ax.bar([i + width/2 for i in x], days_wthr, width,
                label="Weather", color="#E07B54", alpha=0.85)

# Threshold lines
ax.axhline(ALERT_DAYS,   color="red",    linestyle="--", linewidth=1.2,
           label=f"Alert threshold ({ALERT_DAYS}d)")
ax.axhline(CAUTION_DAYS, color="orange", linestyle="--", linewidth=1.2,
           label=f"Caution threshold ({CAUTION_DAYS}d)")

# Annotate bars that hit the ceiling
for bars, vals in [(bars_b, days_base), (bars_w, days_wthr)]:
    for bar, v in zip(bars, vals):
        if v >= HORIZON + 1:
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.3,
                    f">{HORIZON}", ha="center", va="bottom", fontsize=7, color="gray")

ax.set_xticks(list(x))
ax.set_xticklabels(items_plot, rotation=20, ha="right")
ax.set_ylabel("Days until stock-out")
ax.set_title("Stock-Out Risk Ranking by Item\n(shorter bar = higher risk)")
ax.legend(loc="upper left", fontsize=8)
ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
ax.set_ylim(0, HORIZON + 3)
plt.tight_layout()
fig.savefig("output/figures/fig1_stockout_risk.png", dpi=150)
plt.close(fig)
print("Saved → output/figures/fig1_stockout_risk.png")

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE 2 — Inventory Depletion Curves
# ══════════════════════════════════════════════════════════════════════════════
item_ids = summary_sorted["item_id"].tolist()
n_items  = len(item_ids)
ncols    = 4
nrows    = -(-n_items // ncols)   # ceiling division

fig, axes = plt.subplots(nrows, ncols, figsize=(14, 3.5 * nrows), sharey=False)
axes_flat = axes.flatten() if n_items > 1 else [axes]

for ax, item_id in zip(axes_flat, item_ids):
    item_sim  = sim_df[sim_df["item_id"] == item_id].sort_values("day")
    item_name = item_sim["item_name"].iloc[0]
    days      = item_sim["day"].tolist()

    ax.plot(days, item_sim["remaining_baseline"], label="Baseline",
            color="#7BA7BC", linewidth=1.8)
    ax.plot(days, item_sim["remaining_weather"],  label="Weather",
            color="#E07B54", linewidth=1.8, linestyle="--")
    ax.axhline(0, color="red", linewidth=0.8, linestyle=":")
    ax.set_title(item_name, fontsize=10)
    ax.set_xlabel("Day", fontsize=8)
    ax.set_ylabel("Units remaining", fontsize=8)
    ax.legend(fontsize=7)
    ax.tick_params(labelsize=7)

# Hide any unused subplots
for ax in axes_flat[n_items:]:
    ax.set_visible(False)

fig.suptitle("Inventory Depletion Curves (14-day forecast window)", fontsize=12, y=1.01)
plt.tight_layout()
fig.savefig("output/figures/fig2_depletion_curves.png", dpi=150, bbox_inches="tight")
plt.close(fig)
print("Saved → output/figures/fig2_depletion_curves.png")

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE 3 — Model Comparison (MAE improvement)
# ══════════════════════════════════════════════════════════════════════════════
metrics_sorted = metrics.sort_values("delta_mae", ascending=False)

fig, ax = plt.subplots(figsize=(9, 4))
colors = ["#E07B54" if d > 0 else "#AAAAAA" for d in metrics_sorted["delta_mae"]]
x_pos = range(len(metrics_sorted))
ax.bar(x_pos, metrics_sorted["delta_mae"], color=colors, alpha=0.85)
ax.set_xticks(list(x_pos))
ax.set_xticklabels(metrics_sorted["item_name"].tolist(), rotation=20, ha="right")

ax.axhline(0, color="black", linewidth=0.8)
ax.axhline(0.5, color="green", linestyle="--", linewidth=1,
           label="Meaningful improvement threshold (0.5)")
ax.set_ylabel("ΔMAE  (baseline − weather)  [positive = weather helps]")
ax.set_title("Forecast Error Improvement from Weather Regressors (ΔMAE)")
ax.legend(fontsize=8)
plt.tight_layout()
fig.savefig("output/figures/fig3_model_comparison.png", dpi=150)
plt.close(fig)
print("Saved → output/figures/fig3_model_comparison.png")

"""
Reproducible CBP Bar Chart — 2023 Employment by Selected Geography

Source:
  U.S. Census Bureau, County Business Patterns (CBP), 2023.

Scope:
  NAICS2017 00 — Total for all sectors
  LFO 001 — All legal forms
  EMPSZES 001 — All establishment sizes
  Geographies: Delaware, District of Columbia, Maryland,
               Pennsylvania, and Virginia

Measure:
  EMP — employment.

Input:
  ../data/validated/cbp_2023_validated.csv

Output:
  ../results/charts/CBP_BarChart_2023_Employment.png

This script uses the validated stable snapshot. It does not call the Census API.
"""

from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data" / "validated" / "cbp_2023_validated.csv"
OUT = HERE.parent / "results" / "charts" / "CBP_BarChart_2023_Employment.png"

EXPECTED_STATES = {"10", "11", "24", "42", "51"}

df = pd.read_csv(
    DATA,
    dtype={
        "state": "string",
        "NAICS2017": "string",
        "LFO": "string",
        "EMPSZES": "string",
        "YEAR": "string",
    },
)

required = {
    "NAME", "EMP", "EMP_N", "NAICS2017", "NAICS2017_LABEL",
    "LFO", "EMPSZES", "state", "YEAR"
}
missing = required - set(df.columns)
if missing:
    raise ValueError(f"Missing required columns: {sorted(missing)}")

df["state"] = df["state"].str.zfill(2)
df["NAICS2017"] = df["NAICS2017"].str.zfill(2)
df["LFO"] = df["LFO"].str.zfill(3)
df["EMPSZES"] = df["EMPSZES"].str.zfill(3)
df["EMP"] = pd.to_numeric(df["EMP"], errors="raise")
df["EMP_N"] = pd.to_numeric(df["EMP_N"], errors="coerce")

if set(df["state"]) != EXPECTED_STATES:
    raise ValueError("Unexpected geography coverage.")
if not (df["YEAR"] == "2023").all():
    raise ValueError("Input contains a year other than 2023.")
if not (df["NAICS2017"] == "00").all():
    raise ValueError("Expected NAICS2017 code 00 (Total for all sectors).")
if not (df["LFO"] == "001").all() or not (df["EMPSZES"] == "001").all():
    raise ValueError("Expected all legal forms and all establishment sizes.")
if df["EMP"].isna().any() or (df["EMP"] < 0).any():
    raise ValueError("EMP contains missing or negative values.")

# Sort ascending so the largest value appears at the top of a horizontal chart.
plot_df = df.sort_values(["EMP", "NAME"], ascending=[True, True]).copy()

fig, ax = plt.subplots(figsize=(10, 6.2))
bars = ax.barh(plot_df["NAME"], plot_df["EMP"])

ax.set_title(
    "Employment by Selected Geography, 2023",
    loc="left",
    fontsize=16,
    fontweight="bold",
    pad=14,
)
ax.text(
    0, 1.01,
    "County Business Patterns • Total for all sectors",
    transform=ax.transAxes,
    ha="left", va="bottom", fontsize=10,
)

ax.set_xlabel("Employment")
ax.set_ylabel("")
ax.set_xlim(left=0)
ax.xaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{x/1_000_000:.1f}M"))
ax.grid(axis="x", linewidth=0.6, alpha=0.35)
ax.set_axisbelow(True)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

max_emp = plot_df["EMP"].max()
ax.set_xlim(0, max_emp * 1.18)

for bar, value in zip(bars, plot_df["EMP"]):
    ax.text(
        value + max_emp * 0.015,
        bar.get_y() + bar.get_height() / 2,
        f"{value:,.0f}",
        va="center",
        ha="left",
        fontsize=10,
    )

fig.text(
    0.01, 0.01,
    "Source: U.S. Census Bureau, County Business Patterns (CBP), 2023. "
    "NAICS2017 00 (Total for all sectors).",
    ha="left", va="bottom", fontsize=8,
)

plt.tight_layout(rect=[0, 0.05, 1, 1])
OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT, dpi=300, bbox_inches="tight")
plt.close(fig)

print(f"Saved: {OUT}")
print(plot_df[["state", "NAME", "EMP", "EMP_N"]].to_string(index=False))

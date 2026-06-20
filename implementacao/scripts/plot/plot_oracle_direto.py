"""
plot_boxplot.py
Generates one PDF per boxplot from a Hyperledger Besu ZKP benchmark CSV.

PDFs saved to boxplot_oracle/:
  01_tx_seconds_overall.pdf        - tx_seconds for all transactions
  02_tx_seconds_by_scenario.pdf    - tx_seconds grouped by scenario
  03_tx_wait_seconds.pdf           - confirmation wait time
  04_zk_proof_seconds.pdf          - ZK Proof generation time
  05_oracle_process_seconds.pdf    - Oracle processing time
  06_tx_seconds_by_block.pdf       - scatter tx_seconds vs block_number

Usage:
    python plot_boxplot.py [file.csv] [--outdir folder]

Examples:
    python plot_boxplot.py benchmark.csv
    python plot_boxplot.py benchmark.csv --outdir boxplot_oracle
    python plot_boxplot.py  # defaults to data.csv and boxplot_oracle/
"""

import argparse
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages

# ── Arguments ────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Separate boxplots -> PDFs in folder")
parser.add_argument("csv", nargs="?", default="data.csv", help="Input CSV file")
parser.add_argument("--outdir", default="boxplot_oracle", help="Output folder")
args = parser.parse_args()

os.makedirs(args.outdir, exist_ok=True)

# ── Load data ────────────────────────────────────────────────────────────────
df = pd.read_csv(args.csv)
tx = df[df["record_type"] == "tx"].copy()

for col in ["tx_seconds", "tx_wait_seconds", "zk_proof_seconds",
            "oracle_process_seconds", "block_number"]:
    tx[col] = pd.to_numeric(tx[col], errors="coerce")

# ── Helpers ──────────────────────────────────────────────────────────────────
BLUE   = "#1f77b4"
ORANGE = "#ff7f0e"
GREEN  = "#2ca02c"
RED    = "#d62728"
PURPLE = "#9467bd"

BOX_STYLE = dict(
    patch_artist=True,
    medianprops=dict(color="white", linewidth=2.5),
    whiskerprops=dict(linewidth=1.5),
    capprops=dict(linewidth=1.5),
    flierprops=dict(marker="o", markersize=5, linestyle="none", alpha=0.6),
)

def color_boxes(bp, colors):
    if isinstance(colors, str):
        colors = [colors] * len(bp["boxes"])
    for patch, c in zip(bp["boxes"], colors):
        patch.set_facecolor(c)
        patch.set_alpha(0.75)
    for flier, c in zip(bp["fliers"], colors):
        flier.set(markerfacecolor=c, markeredgecolor=c)

def stats_annotation(ax, data, x=0.5, y=-0.11):
    d = data.dropna()
    text = (f"n={len(d)}   min={d.min():.3f}s   "
            f"med={d.median():.3f}s   max={d.max():.3f}s   sigma={d.std():.3f}s")
    ax.text(x, y, text, transform=ax.transAxes,
            ha="center", fontsize=8.5, color="#555")

def save_pdf(fig, filename, title="", subject=""):
    path = os.path.join(args.outdir, filename)
    with PdfPages(path) as pdf:
        pdf.savefig(fig, bbox_inches="tight")
        d = pdf.infodict()
        d["Title"]   = title
        d["Author"]  = "plot_boxplot.py"
        d["Subject"] = subject
    plt.close(fig)
    print(f"  OK  {path}")

# ── 01 · tx_seconds overall ──────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(7, 7))
bp = ax.boxplot(tx["tx_seconds"].dropna(), **BOX_STYLE)
color_boxes(bp, BLUE)
ax.set_ylabel("Time (s)", fontsize=11)
ax.set_xticks([1]); ax.set_xticklabels(["tx_seconds"])
ax.grid(axis="y", linestyle="--", alpha=0.5)
ax.set_facecolor("#f9f9f9")
stats_annotation(ax, tx["tx_seconds"])
plt.tight_layout()
save_pdf(fig, "01_tx_seconds_overall.pdf",
         title="tx_seconds - Overall", subject="Total transaction time")

# ── 02 · tx_seconds by scenario ─────────────────────────────────────────────
scenarios = tx["scenario"].dropna().unique()
data_by_s = [tx.loc[tx["scenario"] == s, "tx_seconds"].dropna() for s in scenarios]
pal = [BLUE, ORANGE, GREEN, RED, PURPLE, "#8c564b"][:len(scenarios)]

fig, ax = plt.subplots(figsize=(max(7, len(scenarios) * 2.5), 7))
bp = ax.boxplot(data_by_s, **BOX_STYLE)
color_boxes(bp, pal)
ax.set_ylabel("Time (s)", fontsize=11)
ax.set_xticks(range(1, len(scenarios) + 1))
ax.set_xticklabels(scenarios, rotation=20, ha="right", fontsize=10)
ax.grid(axis="y", linestyle="--", alpha=0.5)
ax.set_facecolor("#f9f9f9")
plt.tight_layout()
save_pdf(fig, "02_tx_seconds_by_scenario.pdf",
         title="tx_seconds - By Scenario", subject="Scenario comparison")

# ── 03 · tx_wait_seconds ────────────────────────────────────────────────────
if tx["tx_wait_seconds"].notna().sum() > 0:
    fig, ax = plt.subplots(figsize=(7, 7))
    bp = ax.boxplot(tx["tx_wait_seconds"].dropna(), **BOX_STYLE)
    color_boxes(bp, ORANGE)
    ax.set_ylabel("Time (s)", fontsize=11)
    ax.set_xticks([1]); ax.set_xticklabels(["tx_wait_seconds"])
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.set_facecolor("#f9f9f9")
    stats_annotation(ax, tx["tx_wait_seconds"])
    plt.tight_layout()
    save_pdf(fig, "03_tx_wait_seconds.pdf",
             title="tx_wait_seconds", subject="Confirmation wait time")

# ── 04 · zk_proof_seconds ───────────────────────────────────────────────────
if tx["zk_proof_seconds"].notna().sum() > 0:
    fig, ax = plt.subplots(figsize=(7, 7))
    bp = ax.boxplot(tx["zk_proof_seconds"].dropna(), **BOX_STYLE)
    color_boxes(bp, GREEN)
    ax.set_ylabel("Time (s)", fontsize=11)
    ax.set_xticks([1]); ax.set_xticklabels(["zk_proof_seconds"])
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.set_facecolor("#f9f9f9")
    stats_annotation(ax, tx["zk_proof_seconds"])
    plt.tight_layout()
    save_pdf(fig, "04_zk_proof_seconds.pdf",
             title="zk_proof_seconds", subject="ZK Proof generation time")

# ── 05 · oracle_process_seconds ─────────────────────────────────────────────
if tx["oracle_process_seconds"].notna().sum() > 0:
    fig, ax = plt.subplots(figsize=(7, 7))
    bp = ax.boxplot(tx["oracle_process_seconds"].dropna(), **BOX_STYLE)
    color_boxes(bp, RED)
    ax.set_ylabel("Time (s)", fontsize=11)
    ax.set_xticks([1]); ax.set_xticklabels(["oracle_process_seconds"])
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.set_facecolor("#f9f9f9")
    stats_annotation(ax, tx["oracle_process_seconds"])
    plt.tight_layout()
    save_pdf(fig, "05_oracle_process_seconds.pdf",
             title="oracle_process_seconds", subject="Oracle processing time")

# ── 06 · scatter tx_seconds x block_number ──────────────────────────────────
if tx["block_number"].notna().sum() > 0:
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(tx["block_number"], tx["tx_seconds"],
               color=BLUE, alpha=0.75, edgecolors="white", linewidths=0.5, s=70)
    valid = tx[["block_number", "tx_seconds"]].dropna()
    z = np.polyfit(valid["block_number"], valid["tx_seconds"], 1)
    xline = np.linspace(valid["block_number"].min(), valid["block_number"].max(), 300)
    ax.plot(xline, np.poly1d(z)(xline), "--", color=RED, linewidth=1.8, label="Linear trend")
    ax.set_xlabel("Block Number", fontsize=11)
    ax.set_ylabel("Time (s)", fontsize=11)
    ax.legend(fontsize=10)
    ax.grid(linestyle="--", alpha=0.4)
    ax.set_facecolor("#f9f9f9")
    plt.tight_layout()
    save_pdf(fig, "06_tx_seconds_by_block.pdf",
             title="tx_seconds by Block Number", subject="Temporal evolution")


# ── 07 · gas_used overall ────────────────────────────────────────────────────
tx["gas_used"] = pd.to_numeric(tx["gas_used"], errors="coerce")

if tx["gas_used"].notna().sum() > 0:
    fig, ax = plt.subplots(figsize=(7, 7))
    bp = ax.boxplot(tx["gas_used"].dropna(), **BOX_STYLE)
    color_boxes(bp, PURPLE)
    ax.set_ylabel("Gas Used", fontsize=11)
    ax.set_xticks([1]); ax.set_xticklabels(["gas_used"])
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.set_facecolor("#f9f9f9")
    d = tx["gas_used"].dropna()
    ax.text(0.5, -0.11,
            f"n={len(d)}   min={d.min():,.0f}   med={d.median():,.0f}   max={d.max():,.0f}   sigma={d.std():,.0f}",
            transform=ax.transAxes, ha="center", fontsize=8.5, color="#555")
    plt.tight_layout()
    save_pdf(fig, "07_gas_used_overall.pdf",
             title="gas_used - Overall", subject="Gas used per transaction")

# ── 08 · gas_used by scenario ────────────────────────────────────────────────
if tx["gas_used"].notna().sum() > 0:
    scenarios_g = tx["scenario"].dropna().unique()
    data_gas = [tx.loc[tx["scenario"] == s, "gas_used"].dropna() for s in scenarios_g]
    pal_g = [BLUE, ORANGE, GREEN, RED, PURPLE, "#8c564b"][:len(scenarios_g)]

    fig, ax = plt.subplots(figsize=(max(7, len(scenarios_g) * 2.5), 7))
    bp = ax.boxplot(data_gas, **BOX_STYLE)
    color_boxes(bp, pal_g)
    ax.set_ylabel("Gas Used", fontsize=11)
    ax.set_xticks(range(1, len(scenarios_g) + 1))
    ax.set_xticklabels(scenarios_g, rotation=20, ha="right", fontsize=10)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.set_facecolor("#f9f9f9")
    plt.tight_layout()
    save_pdf(fig, "08_gas_used_by_scenario.pdf",
             title="gas_used - By Scenario", subject="Gas used comparison by scenario")

print(f"\nDone. PDFs saved to: {args.outdir}/")
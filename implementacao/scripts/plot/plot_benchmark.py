#!/usr/bin/env python3
"""
Generates benchmark performance charts per scenario, saved as individual PDFs.

Output structure:
  <output_dir>/
    experiment_1/          direct
    experiment_2/          pseudonym / direct_pseudonym
    experiment_3/          oracle
    experiment_3_direto/   oracle_direto
    experiment_4/          redeem / redeem_pseudonym
    cross/                 cross-scenario boxplots
      boxplot_client_pseudonym_gen.pdf
      boxplot_client_zkp_proof.pdf
      boxplot_oracle_processing.pdf
      boxplot_gas_used.pdf

Usage:
  python3 plot_benchmark.py <benchmark_results.csv> [--output-dir <dir>]
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Scenario → experiment mapping
# ---------------------------------------------------------------------------

SCENARIO_TO_EXPERIMENT: Dict[str, str] = {
    "direct":            "experiment_1",
    "pseudonym":         "experiment_2",
    "direct_pseudonym":  "experiment_2",
    "oracle":            "experiment_3",
    "oracle_direto":     "experiment_3_direto",
    "redeem":            "experiment_4",
    "redeem_pseudonym":  "experiment_4",
}

# Human-readable labels for experiment folders
EXPERIMENT_LABELS: Dict[str, str] = {
    "experiment_1":        "Direct Send",
    "experiment_2":        "Pseudonym Send",
    "experiment_3":        "Oracle (with offset)",
    "experiment_3_direto": "Oracle (without offset)",
    "experiment_4":        "ZKP Redeem",
}

# Histogram metrics per experiment: (column, x-axis label)
EXPERIMENT_METRICS: Dict[str, List[Tuple[str, str]]] = {
    "experiment_1": [
        ("tx_wait_seconds", "Transaction time (s)"),
    ],
    "experiment_2": [
        ("tx_wait_seconds",       "Transaction time (s)"),
        ("pseudonym_gen_seconds", "Pseudonym generation time (s)"),
    ],
    "experiment_3": [
        ("oracle_process_seconds", "Oracle processing time (s)"),
        ("oracle_confirm_seconds", "Oracle confirmation time (s)"),
        ("tx_wait_seconds",        "Blockchain confirmation time (s)"),
        ("zk_proof_seconds",       "ZKP proof generation time (s)"),
    ],
    "experiment_3_direto": [
        ("tx_wait_seconds", "Transaction time (s)"),
    ],
    "experiment_4": [
        ("zk_proof_seconds", "ZKP proof generation time (s)"),
        ("tx_wait_seconds",  "Transaction time incl. ZKP verification (s)"),
    ],
}

# Boxplot metrics per experiment: (column, tick label)
EXPERIMENT_BOXPLOT_METRICS: Dict[str, List[Tuple[str, str]]] = {
    "experiment_1":        [("tx_wait_seconds",        "Transaction\ntime (s)")],
    "experiment_2":        [("pseudonym_gen_seconds",  "Pseudonym\ngeneration (s)")],
    "experiment_3":        [("oracle_process_seconds", "Oracle\nprocessing (s)")],
    "experiment_3_direto": [("tx_wait_seconds",        "Transaction\ntime (s)")],
    "experiment_4": [
        ("zk_proof_seconds", "ZKP proof\ngeneration (s)"),
        ("tx_wait_seconds",  "Transaction incl.\nZKP verification (s)"),
    ],
}

PALETTE = [
    "#2196F3", "#9C27B0", "#00897B", "#F4511E",
    "#039BE5", "#8E24AA", "#00ACC1", "#E53935",
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_results(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df = df[df["record_type"] == "tx"].copy()
    numeric_cols = [
        "tx_seconds", "tx_wait_seconds", "oracle_process_seconds",
        "oracle_confirm_seconds", "zk_proof_seconds", "pseudonym_gen_seconds",
        "gas_used", "e1_original_micro", "e1_after_micro",
        "e1_original_brl", "e1_after_brl", "tx_status",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------

def pct(values: pd.Series, p: float) -> float:
    v = values.dropna()
    return float(np.percentile(v, p)) if not v.empty else 0.0


def stats_dict(v: pd.Series) -> dict:
    v = v.dropna()
    if v.empty:
        return {}
    return {
        "n":      len(v),
        "mean":   v.mean(),
        "median": v.median(),
        "std":    v.std(),
        "min":    v.min(),
        "p25":    pct(v, 25),
        "p75":    pct(v, 75),
        "p95":    pct(v, 95),
        "max":    v.max(),
    }


# ---------------------------------------------------------------------------
# Core plot functions (no titles)
# ---------------------------------------------------------------------------

def _no_data(ax: plt.Axes) -> None:
    ax.text(0.5, 0.5, "No data", ha="center", va="center",
            transform=ax.transAxes, fontsize=12, color="gray")
    ax.axis("off")


def plot_histogram(ax: plt.Axes, values: pd.Series, xlabel: str, color: str) -> None:
    v = values.dropna()
    if v.empty:
        _no_data(ax)
        return

    s = stats_dict(v)
    n_bins = min(40, max(10, len(v) // 5))

    ax.hist(v, bins=n_bins, color=color, alpha=0.75, edgecolor="white", linewidth=0.5)
    ax.axvline(s["mean"],   color="#E53935", linewidth=2.0, linestyle="--",
               label=f"Mean: {s['mean']:.3f}s")
    ax.axvline(s["median"], color="#43A047", linewidth=2.0, linestyle="-.",
               label=f"Median: {s['median']:.3f}s")
    ax.axvline(s["p95"],    color="#FB8C00", linewidth=1.5, linestyle=":",
               label=f"P95: {s['p95']:.3f}s")

    ax.set_xlabel(xlabel, fontsize=9)
    ax.set_ylabel("Frequency", fontsize=9)
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)

    info = (f"n={s['n']}   sd={s['std']:.3f}s   "
            f"min={s['min']:.3f}s   max={s['max']:.3f}s")
    ax.text(0.98, 0.97, info, transform=ax.transAxes,
            ha="right", va="top", fontsize=7.5,
            bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.8))


def plot_boxplot(
    ax: plt.Axes,
    series_list: List[pd.Series],
    tick_labels: List[str],
    ylabel: str = "Time (s)",
) -> None:
    """Boxplot with mean marker. No title."""
    plot_data = [v.dropna().values for v in series_list]
    non_empty = [(d, l) for d, l in zip(plot_data, tick_labels) if len(d) > 0]

    if not non_empty:
        _no_data(ax)
        return

    data_f, labels_f = zip(*non_empty)

    bp = ax.boxplot(
        data_f,
        tick_labels=labels_f,
        patch_artist=True,
        notch=False,
        showfliers=True,
        flierprops=dict(marker="o", markersize=3, alpha=0.4,
                        markerfacecolor="#607D8B", markeredgecolor="none"),
        medianprops=dict(color="#43A047", linewidth=2.5),
        whiskerprops=dict(linewidth=1.2),
        capprops=dict(linewidth=1.5),
        boxprops=dict(linewidth=1.2),
    )

    for patch, color in zip(bp["boxes"], PALETTE):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)

    for i, d in enumerate(data_f, start=1):
        ax.plot(i, float(np.mean(d)), marker="^", color="#E53935",
                markersize=8, zorder=5, label="Mean" if i == 1 else "")

    ax.set_ylabel(ylabel, fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    ax.tick_params(axis="x", labelsize=8)

    legend_elements = [
        Line2D([0], [0], marker="^", color="w", markerfacecolor="#E53935",
               markersize=8, label="Mean"),
        Line2D([0], [0], color="#43A047", linewidth=2.5, label="Median"),
    ]
    ax.legend(handles=legend_elements, fontsize=8, loc="upper right")


# ---------------------------------------------------------------------------
# PDF savers
# ---------------------------------------------------------------------------

def save_fig(fig: plt.Figure, path: Path, pdf_title: str = "") -> None:
    with PdfPages(str(path)) as pdf:
        pdf.savefig(fig, bbox_inches="tight")
        d = pdf.infodict()
        d["Title"]  = pdf_title or path.stem
        d["Author"] = "plot_benchmark.py"
    plt.close(fig)
    print(f"    [ok] {path.name}")


# ---------------------------------------------------------------------------
# Per-experiment generators
# ---------------------------------------------------------------------------

def generate_summary_table(
    exp_key: str,
    df_ok: pd.DataFrame,
    metrics: List[Tuple[str, str]],
    out_dir: Path,
) -> None:
    rows = []
    for col, label in metrics:
        if col not in df_ok.columns:
            continue
        s = stats_dict(df_ok[col])
        if not s:
            continue
        rows.append({
            "Metric":    label,
            "n":         s["n"],
            "Mean (s)":  f"{s['mean']:.4f}",
            "Median (s)": f"{s['median']:.4f}",
            "SD (s)":    f"{s['std']:.4f}",
            "Min (s)":   f"{s['min']:.4f}",
            "P25 (s)":   f"{s['p25']:.4f}",
            "P75 (s)":   f"{s['p75']:.4f}",
            "P95 (s)":   f"{s['p95']:.4f}",
            "Max (s)":   f"{s['max']:.4f}",
        })

    fig_h = max(2.5, 0.7 * (len(rows) + 2))
    fig, ax = plt.subplots(figsize=(16, fig_h))
    ax.axis("off")

    if not rows:
        ax.text(0.5, 0.5, "No data available", ha="center", va="center",
                fontsize=12, color="gray")
    else:
        df_t = pd.DataFrame(rows)
        tbl = ax.table(
            cellText=df_t.values.tolist(),
            colLabels=list(df_t.columns),
            cellLoc="center",
            loc="center",
        )
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(8.5)
        tbl.scale(1, 1.6)
        for j in range(len(df_t.columns)):
            tbl[0, j].set_facecolor("#1565C0")
            tbl[0, j].set_text_props(color="white", fontweight="bold")
        for i in range(1, len(rows) + 1):
            bg = "#E3F2FD" if i % 2 == 0 else "white"
            for j in range(len(df_t.columns)):
                tbl[i, j].set_facecolor(bg)

    fig.tight_layout()
    save_fig(fig, out_dir / "summary.pdf", f"Summary — {EXPERIMENT_LABELS.get(exp_key, exp_key)}")


def generate_histograms(
    exp_key: str,
    df_ok: pd.DataFrame,
    metrics: List[Tuple[str, str]],
    out_dir: Path,
) -> None:
    for i, (col, label) in enumerate(metrics):
        if col not in df_ok.columns or df_ok[col].dropna().empty:
            continue
        fig, ax = plt.subplots(figsize=(9, 5))
        plot_histogram(ax, df_ok[col], label, color=PALETTE[i % len(PALETTE)])
        fig.tight_layout()
        save_fig(fig, out_dir / f"histogram_{col}.pdf",
                 f"{EXPERIMENT_LABELS.get(exp_key, exp_key)} — {label}")


def generate_experiment_boxplot(
    exp_key: str,
    df_ok: pd.DataFrame,
    out_dir: Path,
) -> None:
    metrics = EXPERIMENT_BOXPLOT_METRICS.get(exp_key, [])
    valid = [
        (col, lbl) for col, lbl in metrics
        if col in df_ok.columns and not df_ok[col].dropna().empty
    ]
    if not valid:
        return

    fig_w = max(7, 2.5 * len(valid))
    fig, ax = plt.subplots(figsize=(fig_w, 6))
    plot_boxplot(ax, [df_ok[col] for col, _ in valid], [lbl for _, lbl in valid])
    fig.tight_layout()
    save_fig(fig, out_dir / "boxplot.pdf",
             f"Boxplot — {EXPERIMENT_LABELS.get(exp_key, exp_key)}")


def generate_e1_histogram(
    exp_key: str,
    df_ok: pd.DataFrame,
    out_dir: Path,
) -> None:
    col = "e1_after_brl"
    if col not in df_ok.columns or df_ok[col].dropna().empty:
        return
    fig, ax = plt.subplots(figsize=(9, 5))
    plot_histogram(ax, df_ok[col], "Monetized value E1 (BRL)", color="#43A047")
    fig.tight_layout()
    save_fig(fig, out_dir / "e1_distribution.pdf",
             f"{EXPERIMENT_LABELS.get(exp_key, exp_key)} — E1 Distribution")


def build_experiment(
    exp_key: str,
    df_exp: pd.DataFrame,
    base_output_dir: Path,
) -> None:
    metrics = EXPERIMENT_METRICS.get(exp_key, [])
    out_dir = base_output_dir / exp_key
    out_dir.mkdir(parents=True, exist_ok=True)

    if "tx_status" in df_exp.columns:
        df_ok = df_exp[df_exp["tx_status"] == 1].copy()
    else:
        df_ok = df_exp.copy()

    label = EXPERIMENT_LABELS.get(exp_key, exp_key)
    print(f"\n  {exp_key} ({label})")
    print(f"    Total: {len(df_exp)}  |  Success: {len(df_ok)}")
    print(f"    Dir: {out_dir}")

    generate_summary_table(exp_key, df_ok, metrics, out_dir)
    generate_histograms(exp_key, df_ok, metrics, out_dir)
    generate_experiment_boxplot(exp_key, df_ok, out_dir)
    generate_e1_histogram(exp_key, df_ok, out_dir)


# ---------------------------------------------------------------------------
# Cross-scenario boxplots
# ---------------------------------------------------------------------------

def generate_cross_boxplots(df: pd.DataFrame, base_output_dir: Path) -> None:
    """
    Generates cross-scenario boxplots in <output_dir>/cross/:

    1. boxplot_client_pseudonym_gen.pdf
       — pseudonym_gen_seconds for pseudonym / direct_pseudonym

    2. boxplot_client_zkp_proof.pdf
       — zk_proof_seconds for redeem / redeem_pseudonym

    3. boxplot_oracle_processing.pdf
       — oracle_process_seconds for oracle / oracle_direto
         (oracle_direto uses tx_wait_seconds as proxy since it calls
          /registrar_trajeto in a single round-trip)

    4. boxplot_gas_used.pdf
       — gas_used for direct, oracle_direto and redeem / redeem_pseudonym
    """
    cross_dir = base_output_dir / "cross"
    cross_dir.mkdir(parents=True, exist_ok=True)

    print("\n  cross-scenario boxplots")
    print(f"    Dir: {cross_dir}")

    # Filter successes only
    if "tx_status" in df.columns:
        df_ok = df[df["tx_status"] == 1].copy()
    else:
        df_ok = df.copy()

    def sc(scenario: str, col: str) -> pd.Series:
        """Returns column values for a specific scenario (successes only)."""
        if col not in df_ok.columns:
            return pd.Series(dtype=float)
        return df_ok.loc[df_ok["scenario"] == scenario, col]

    # ------------------------------------------------------------------
    # 1 & 2. Client — pseudonym generation + proof generation (same plot)
    # ------------------------------------------------------------------
    series_pseudo = pd.concat([
        sc("pseudonym", "pseudonym_gen_seconds"),
        sc("direct_pseudonym", "pseudonym_gen_seconds"),
    ]).dropna()

    series_zkp = pd.concat([
        sc("redeem", "zk_proof_seconds"),
        sc("redeem_pseudonym", "zk_proof_seconds"),
    ]).dropna()

    client_series = []
    client_labels = []
    if not series_pseudo.empty:
        client_series.append(series_pseudo)
        client_labels.append("Pseudonym\ngeneration (s)")
    if not series_zkp.empty:
        client_series.append(series_zkp)
        client_labels.append("Proof\ngeneration (s)")

    if client_series:
        fig_w = max(5, 3.5 * len(client_series))
        fig, ax = plt.subplots(figsize=(fig_w, 6))
        plot_boxplot(ax, client_series, client_labels)
        fig.tight_layout()
        save_fig(fig, cross_dir / "boxplot_client_times.pdf",
                 "Client — Pseudonym Generation & Proof Generation")
    else:
        print("    [skip] boxplot_client_times.pdf — no data")

    # ------------------------------------------------------------------
    # 3. Oracle processing time (offset only)
    #    oracle → oracle_process_seconds (time spent generating offset options)
    # ------------------------------------------------------------------
    series_oracle = sc("oracle", "oracle_process_seconds").dropna()

    if not series_oracle.empty:
        fig, ax = plt.subplots(figsize=(5, 6))
        plot_boxplot(ax, [series_oracle], ["Oracle\nprocessing (s)"])
        fig.tight_layout()
        save_fig(fig, cross_dir / "boxplot_oracle_processing.pdf",
                 "Oracle Processing Time")
    else:
        print("    [skip] boxplot_oracle_processing.pdf — no data")

    # ------------------------------------------------------------------
    # 4. Gas used by the smart contract
    #    direct        — mint (no oracle, no ZKP)
    #    oracle_direto — mint via /registrar_trajeto (with ZKP)
    #    redeem        — redeemWithZK
    #    redeem_pseudonym — redeemWithZK (pseudonym)
    # ------------------------------------------------------------------
    gas_configs = [
        ("direct",           "without privacy"),
        ("oracle",           "obfuscation with\nZKP check"),
        ("redeem",           "ZKP Redeem"),
        ("redeem_pseudonym", "ZKP Redeem"),
    ]

    gas_series = []
    gas_labels = []
    for scenario, label in gas_configs:
        s = sc(scenario, "gas_used").dropna()
        if not s.empty:
            gas_series.append(s)
            gas_labels.append(label)

    if gas_series:
        # Convert to Kgas (divide by 1000)
        gas_series_k = [s / 1000.0 for s in gas_series]
        fig_w = max(7, 2.5 * len(gas_series_k))
        fig, ax = plt.subplots(figsize=(fig_w, 6))
        plot_boxplot(ax, gas_series_k, gas_labels, ylabel="Gas units (×1000)")
        fig.tight_layout()
        save_fig(fig, cross_dir / "boxplot_gas_used.pdf",
                 "Smart Contract Gas Usage")
    else:
        print("    [skip] boxplot_gas_used.pdf — no data")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generates benchmark performance charts (one PDF per chart)."
    )
    parser.add_argument(
        "results_csv",
        nargs="?",
        help="Path to benchmark_results.csv",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=None,
        help="Root output directory (default: 'charts' subfolder next to the CSV)",
    )
    args = parser.parse_args()

    # Resolve CSV path
    if args.results_csv:
        csv_path = Path(args.results_csv)
    else:
        script_dir = Path(__file__).resolve().parent
        repo_root  = script_dir.parents[1]
        csv_path   = repo_root / "test" / "results" / "benchmark_results.csv"
        if not csv_path.exists():
            backup_dir = repo_root / "test" / "results" / "backup"
            candidates = sorted(backup_dir.glob("benchmark_results*.csv"))
            if candidates:
                csv_path = candidates[-1]
                print(f"[warning] benchmark_results.csv not found; using: {csv_path.name}")
            else:
                print("[error] No benchmark_results.csv found.", file=sys.stderr)
                sys.exit(1)

    if not csv_path.exists():
        print(f"[error] File not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir) if args.output_dir else csv_path.parent / "charts"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading: {csv_path}")
    df = load_results(str(csv_path))
    print(f"  {len(df)} transaction rows loaded.")

    if df.empty:
        print("[error] No transaction rows found.", file=sys.stderr)
        sys.exit(1)

    # Group rows by experiment key
    experiments: Dict[str, pd.DataFrame] = {}
    for scenario, exp_key in SCENARIO_TO_EXPERIMENT.items():
        df_sc = df[df["scenario"] == scenario]
        if df_sc.empty:
            continue
        if exp_key not in experiments:
            experiments[exp_key] = df_sc
        else:
            experiments[exp_key] = pd.concat(
                [experiments[exp_key], df_sc], ignore_index=True
            )

    if not experiments:
        print("[error] No recognised scenarios found in CSV.", file=sys.stderr)
        print(f"  Scenarios present: {df['scenario'].unique().tolist()}")
        sys.exit(1)

    print(f"\nGenerating charts in: {output_dir}")

    for exp_key in sorted(experiments):
        build_experiment(exp_key, experiments[exp_key], output_dir)

    generate_cross_boxplots(df, output_dir)

    print("\nDone!")
    print("Output structure:")
    for p in sorted(output_dir.rglob("*.pdf")):
        rel = p.relative_to(output_dir)
        print(f"  {rel}")


if __name__ == "__main__":
    main()

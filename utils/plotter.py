"""
utils/plotter.py — Diagnostic plot generation
==============================================
Generates:
  • Availability vs Circuit-Switched traffic (dual-axis line chart)
  • Availability vs Packet-Switched traffic (dual-axis line chart)

These plots replicate the diagnostic visualisations that engineers currently
produce manually in the NMS, and serve as inputs to the ResNet classifier.
"""

import io
from typing import Dict, Tuple

import matplotlib
matplotlib.use("Agg")                        # non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

from utils.config import PLOT_DPI, PLOT_W_IN, PLOT_H_IN


# ── Shared style ───────────────────────────────────────────────────────────────
_BG      = "#0b0f1a"
_SURFACE = "#111827"
_BORDER  = "#1f2d42"
_TEXT    = "#e2e8f0"
_MUTED   = "#64748b"
_AVAIL_C = "#00d4ff"    # cyan  — availability
_CS_C    = "#ff6b35"    # orange — CS traffic
_PS_C    = "#00e5a0"    # green  — PS traffic


def _apply_dark_style(fig, ax_left, ax_right, title: str, cell_id: str):
    """Apply dark-theme styling shared across both plot types."""
    fig.patch.set_facecolor(_BG)
    ax_left.set_facecolor(_SURFACE)

    for spine in ax_left.spines.values():
        spine.set_edgecolor(_BORDER)
    for spine in ax_right.spines.values():
        spine.set_edgecolor(_BORDER)

    ax_left.tick_params(colors=_MUTED, labelsize=7)
    ax_right.tick_params(colors=_MUTED, labelsize=7)
    ax_left.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %Hh"))
    ax_left.xaxis.set_major_locator(mdates.DayLocator())
    plt.setp(ax_left.xaxis.get_majorticklabels(), rotation=30, ha="right")

    fig.suptitle(f"{title}\n{cell_id}", color=_TEXT, fontsize=9, fontweight="bold", y=0.99)
    ax_left.grid(True, color=_BORDER, linewidth=0.5, linestyle="--", alpha=0.7)


def generate_plots(
    cell_id: str,
    df: pd.DataFrame,
) -> Dict[str, bytes]:
    """
    Generate diagnostic plot(s) for a single cell.

    Produces the Availability-vs-PS plot for every cell, plus the
    Availability-vs-CS plot only when the cell carries circuit-switched
    traffic (2G/3G). 4G/5G cells therefore yield a single plot.

    Returns
    -------
    {"ps": bytes}                or  {"cs": bytes, "ps": bytes}
    """
    ts    = pd.to_datetime(df["timestamp"])
    avail = df["availability"]

    out: Dict[str, bytes] = {}

    has_cs = df.attrs.get("has_cs", "cs_traffic" in df.columns) and "cs_traffic" in df.columns
    if has_cs:
        out["cs"] = _make_plot(
            ts, avail, df["cs_traffic"],
            right_label="CS Traffic Volume (Erlangs)",
            right_color=_CS_C,
            title="Cell Availability vs Circuit-Switched Traffic",
            cell_id=cell_id,
        )

    out["ps"] = _make_plot(
        ts, avail, df["ps_traffic"],
        right_label="PS Traffic Volume (MB/h)",
        right_color=_PS_C,
        title="Cell Availability vs Packet-Switched Traffic",
        cell_id=cell_id,
    )
    return out


def _make_plot(
    ts, avail, traffic,
    right_label: str,
    right_color: str,
    title: str,
    cell_id: str,
) -> bytes:
    fig, ax1 = plt.subplots(figsize=(PLOT_W_IN, PLOT_H_IN), dpi=PLOT_DPI)
    ax2 = ax1.twinx()

    # Plot availability
    ax1.plot(ts, avail, color=_AVAIL_C, linewidth=1.6, label="Availability (%)")
    ax1.fill_between(ts, avail, alpha=0.08, color=_AVAIL_C)
    ax1.set_ylabel("Availability (%)", color=_AVAIL_C, fontsize=8)
    ax1.tick_params(axis="y", labelcolor=_AVAIL_C)
    ax1.set_ylim(0, 105)

    # Plot traffic
    ax2.plot(ts, traffic, color=right_color, linewidth=1.4,
             linestyle="--", label=right_label)
    ax2.fill_between(ts, traffic, alpha=0.06, color=right_color)
    ax2.set_ylabel(right_label, color=right_color, fontsize=8)
    ax2.tick_params(axis="y", labelcolor=right_color)

    _apply_dark_style(fig, ax1, ax2, title, cell_id)

    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(
        lines1 + lines2, labels1 + labels2,
        loc="upper left", fontsize=7,
        facecolor=_SURFACE, edgecolor=_BORDER, labelcolor=_TEXT,
    )

    plt.tight_layout(rect=[0, 0, 1, 0.95])

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=PLOT_DPI, facecolor=_BG)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def generate_all_plots(
    kpi_data: Dict[str, pd.DataFrame],
    progress_callback=None,
) -> Tuple[Dict[str, Dict[str, bytes]], list]:
    """
    Generate CS + PS plots for every cell in kpi_data.

    Returns
    -------
    plots     : {cell_id: {"cs": bytes, "ps": bytes}}
    log_lines : list of status strings
    """
    plots     = {}
    log_lines = []
    total = len(kpi_data)

    for i, (cid, df) in enumerate(kpi_data.items()):
        if progress_callback:
            progress_callback((i + 1) / total, f"Plotting {cid}…")
        try:
            plots[cid] = generate_plots(cid, df)
            kinds = "+".join(plots[cid].keys()).upper()
            log_lines.append(f"Plots generated: {cid} ({kinds})")
        except Exception as e:
            log_lines.append(f"Plot error ({cid}): {e}")

    return plots, log_lines
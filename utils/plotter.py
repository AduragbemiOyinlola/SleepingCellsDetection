"""
utils/plotter.py — Diagnostic plot generation
==============================================
Generates:
  • Availability vs Circuit-Switched traffic (dual-axis line chart)
  • Availability vs Packet-Switched traffic (dual-axis line chart)

These plots replicate the diagnostic visualisations that engineers currently
produce manually in the NMS, and serve as inputs to the ResNet classifier.

Styling matches the training dataset exactly (white background, solid green
availability line, dashed blue traffic line, no title baked into the image)
since the deployed classifier was trained on that visual format and a
mismatch here means degenerate, out-of-distribution predictions. The cell ID
is surfaced separately in the UI (dashboard's selectbox/labels), not inside
the plot image.
"""

import io
from typing import Dict, Tuple

import matplotlib
matplotlib.use("Agg")                        # non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

from utils.config import PLOT_DPI, PLOT_W_IN, PLOT_H_IN


# ── Shared style (matches the training dataset) ────────────────────────────────
_AVAIL_C = "green"    # availability
_CS_C    = "blue"     # CS traffic
_PS_C    = "blue"     # PS traffic


def _apply_style(ax_left, ax_right):
    """Apply the light styling shared across both plot types."""
    ax_left.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    ax_left.xaxis.set_major_locator(mdates.DayLocator())
    ax_left.grid(True, linewidth=0.5, linestyle="--", alpha=0.7)


def generate_plots(
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
        )

    out["ps"] = _make_plot(
        ts, avail, df["ps_traffic"],
        right_label="PS Traffic Volume (MB/h)",
        right_color=_PS_C,
    )
    return out


def _make_plot(
    ts, avail, traffic,
    right_label: str,
    right_color: str,
) -> bytes:
    fig, ax1 = plt.subplots(figsize=(PLOT_W_IN, PLOT_H_IN), dpi=PLOT_DPI)
    ax2 = ax1.twinx()

    # Plot availability
    ax1.plot(ts, avail, color=_AVAIL_C, linewidth=1.6, label="Availability (%)")
    ax1.set_ylabel("Availability (%)", fontsize=8)
    ax1.set_ylim(0, 105)

    # Plot traffic — floor at zero (traffic is physically non-negative, and this
    # matches the training data's axis convention; matplotlib's plain autoscale
    # centers symmetrically around near-constant series instead, which shifts
    # a flat near-zero line to the middle of the frame rather than the bottom)
    ax2.plot(ts, traffic, color=right_color, linewidth=1.4,
             linestyle="--", label=right_label)
    ax2.set_ylabel(right_label, fontsize=8)
    ax2.set_ylim(bottom=0)

    _apply_style(ax1, ax2)

    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=7)

    plt.tight_layout(pad=0.3)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=PLOT_DPI, bbox_inches="tight", pad_inches=0.02)
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
            plots[cid] = generate_plots(df)
            kinds = "+".join(plots[cid].keys()).upper()
            log_lines.append(f"Plots generated: {cid} ({kinds})")
        except Exception as e:
            log_lines.append(f"Plot error ({cid}): {e}")

    return plots, log_lines
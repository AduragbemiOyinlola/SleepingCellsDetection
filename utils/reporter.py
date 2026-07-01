"""
utils/reporter.py — CSV report compilation
"""

import io
from datetime import date
from typing import Dict, List

import pandas as pd


def build_report_csv(
    classifications: Dict[str, Dict],
    sites: List[Dict],
) -> bytes:
    """
    Build the confirmed sleeping cells CSV.

    Parameters
    ----------
    classifications : output of classify_plots()
    sites           : original parsed site list (may have extra metadata cols)

    Returns
    -------
    CSV bytes ready for email attachment or download.
    """
    # Index sites by cell_id for enrichment
    site_meta = {s["cell_id"]: s for s in sites}

    rows = []
    for cid, res in classifications.items():
        if res["final"] != 1:
            continue
        row = {"cell_id": cid, "report_date": date.today().isoformat()}
        row.update({k: v for k, v in site_meta.get(cid, {}).items() if k != "cell_id"})
        row["ps_probability"] = res["ps_prob"]
        row["ps_verdict"]     = "sleeping" if res["ps_label"] else "healthy"
        if res.get("has_cs"):
            row["cs_probability"] = res.get("cs_prob")
            row["cs_verdict"]     = "sleeping" if res.get("cs_label") else "healthy"
        else:
            row["cs_probability"] = "n/a"
            row["cs_verdict"]     = "n/a"
        down = []
        if res.get("has_cs") and res.get("cs_label"):
            down.append("CS")
        if res.get("ps_label"):
            down.append("PS")
        row["streams_down"]   = "+".join(down) if down else ""
        row["final_verdict"]  = "SLEEPING"
        rows.append(row)

    if not rows:
        df = pd.DataFrame(columns=["cell_id", "report_date", "final_verdict"])
    else:
        df = pd.DataFrame(rows)

    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


def summarise(classifications: Dict[str, Dict]) -> Dict:
    total    = len(classifications)
    sleeping = sum(1 for v in classifications.values() if v["final"] == 1)
    return {
        "total":    total,
        "sleeping": sleeping,
        "healthy":  total - sleeping,
        "rate":     round(sleeping / total * 100, 1) if total else 0,
    }
"""
utils/nms_client.py — Network Management System API client
============================================================
Fetches KPI data (availability, CS traffic, PS traffic) for each cell.

Set NMS_MOCK=1 (default) in config.py / env vars to run with synthetic
data without a real NMS connection — useful for development and demos.

Real NMS integration
---------------------
Replace `_fetch_real()` with your operator's REST / SOAP / gRPC calls.
Common NMS platforms and their typical endpoints:

  Nokia NetAct  → REST /api/pm/counters
  Ericsson OSS  → REST /oss/pm/files  or  eNBI-XML pull
  Huawei U2020  → SOAP MO-based PM query

Authentication is usually Bearer token or API-key injected into headers.
"""

import io
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

from utils.config import (
    NMS_MOCK,
    NMS_BASE_URL,
    NMS_API_KEY,
    NMS_TIMEOUT,
    OBS_DAYS,
)


# ─── Public interface ─────────────────────────────────────────────────────────

def tech_has_cs(tech: str) -> bool:
    """4G/5G are packet-only and carry NO circuit-switched traffic.
    2G/3G (and anything unlabelled) are treated as having CS traffic."""
    t = (tech or "").strip().lower().replace(" ", "")
    return t not in ("4g", "lte", "5g", "nr", "5gnr", "4g/5g", "4glte")


def fetch_kpi_data(
    sites,
    progress_callback=None,
) -> Tuple[Dict[str, pd.DataFrame], List[str]]:
    """
    Fetch KPI data for all cells.

    Parameters
    ----------
    sites            : list of site dicts ({"cell_id", "tech", ...}) or plain
                       cell-id strings.
    progress_callback: optional callable(frac: float, label: str) for UI progress

    Returns
    -------
    kpi_data  : dict {cell_id -> DataFrame}. Columns are [timestamp,
                availability, ps_traffic] and additionally cs_traffic only for
                technologies that carry circuit-switched traffic (2G/3G).
                df.attrs carries {"tech", "has_cs"}.
    log_lines : list of status strings
    """
    kpi_data  : Dict[str, pd.DataFrame] = {}
    log_lines : List[str] = []

    norm = []
    for s in sites:
        if isinstance(s, dict):
            norm.append((str(s.get("cell_id", "")).strip(), s.get("tech", "")))
        else:
            norm.append((str(s).strip(), ""))

    for i, (cid, tech) in enumerate(norm):
        if progress_callback:
            progress_callback((i + 1) / len(norm), f"Fetching KPIs for {cid}…")

        if NMS_MOCK:
            df, msg = _fetch_mock(cid, tech)
        else:
            df, msg = _fetch_real(cid)

        kpi_data[cid] = df
        log_lines.append(msg)

    return kpi_data, log_lines


# ─── Mock data generator ──────────────────────────────────────────────────────

# Rough fraction of cells that should be "sleeping" in mock data
_SLEEPING_PROBABILITY = 0.35


def _fetch_mock(cell_id: str, tech: str = "") -> Tuple[pd.DataFrame, str]:
    """Generate realistic synthetic KPI data for demo purposes."""
    time.sleep(0.05)   # tiny delay to feel real

    rng      = random.Random(cell_id)   # deterministic per cell_id
    is_sleep = rng.random() < _SLEEPING_PROBABILITY
    has_cs   = tech_has_cs(tech)

    periods = OBS_DAYS * 24            # hourly samples
    now     = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    timestamps = [now - timedelta(hours=periods - i) for i in range(periods)]

    availability, cs_traffic, ps_traffic = [], [], []
    sleep_start = periods // 3        # fault starts ~33% into window

    for idx, t in enumerate(timestamps):
        hour = t.hour
        daily_factor = 0.4 + 0.6 * abs((hour - 12) / 12)   # 0.4–1.0
        noise = rng.gauss(0, 0.05)
        avail = max(0.0, min(100.0, 97 + rng.gauss(0, 1.5)))

        if is_sleep and idx >= sleep_start:
            cs = max(0.0, rng.gauss(0.5, 0.4))             # near-zero
            ps = max(0.0, rng.gauss(1.2, 0.8))
        else:
            cs = max(0.0, rng.gauss(60, 8)  * daily_factor + noise * 10)
            ps = max(0.0, rng.gauss(800, 80) * daily_factor + noise * 100)

        availability.append(round(avail, 2))
        cs_traffic.append(round(cs, 2))
        ps_traffic.append(round(ps, 2))

    cols = {"timestamp": timestamps, "availability": availability}
    if has_cs:
        cols["cs_traffic"] = cs_traffic
    cols["ps_traffic"] = ps_traffic
    df = pd.DataFrame(cols)
    df.attrs["tech"]        = tech
    df.attrs["has_cs"]      = has_cs
    df.attrs["_is_sleeping"] = is_sleep   # hidden ground truth (mock only)

    status = "MOCK-SLEEPING" if is_sleep else "MOCK-HEALTHY"
    kpis = "avail+cs+ps" if has_cs else "avail+ps (no CS — 4G/5G)"
    return df, f"[{status}] {cell_id} ({tech or 'n/a'}): {periods} records, {kpis}."


# ─── Real NMS integration stub ────────────────────────────────────────────────

def _fetch_real(cell_id: str) -> Tuple[pd.DataFrame, str]:
    """
    Replace this function body with actual NMS API calls.

    Example for a generic REST NMS:
        GET {NMS_BASE_URL}/pm/counters?cell={cell_id}&days={OBS_DAYS}
        Authorization: Bearer {NMS_API_KEY}

    Expected response JSON:
        {
          "cell_id": "...",
          "records": [
            {"timestamp": "2025-04-01T00:00:00Z",
             "availability": 98.2,
             "cs_traffic": 55.3,
             "ps_traffic": 720.1},
            ...
          ]
        }
    """
    headers = {
        "Authorization": f"Bearer {NMS_API_KEY}",
        "Accept":        "application/json",
    }
    params = {
        "cell":  cell_id,
        "days":  OBS_DAYS,
        "kpis":  "availability,cs_traffic,ps_traffic",
    }
    try:
        resp = requests.get(
            f"{NMS_BASE_URL}/pm/counters",
            headers=headers,
            params=params,
            timeout=NMS_TIMEOUT,
        )
        resp.raise_for_status()
        data   = resp.json()
        records = data.get("records", [])
        df = pd.DataFrame(records)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp").reset_index(drop=True)
        return df, f"OK: {cell_id} — {len(df)} records."
    except requests.HTTPError as e:
        return _empty_df(), f"HTTP error for {cell_id}: {e}"
    except Exception as e:
        return _empty_df(), f"Error for {cell_id}: {e}"


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["timestamp", "availability", "cs_traffic", "ps_traffic"])


# ─── CSV parsing ──────────────────────────────────────────────────────────────

def parse_sites_csv(csv_bytes: bytes) -> Tuple[List[Dict], str]:
    """
    Parse the email-attached CSV of suspected sites.

    Expected columns (at minimum): cell_id
    Optional: site_name, region, vendor, ...

    Returns (list of row dicts, log message).
    """
    try:
        df = pd.read_csv(io.BytesIO(csv_bytes))
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

        # Try common column name variants for cell_id
        for candidate in ("cell_id", "cellid", "cell", "site_id", "node_id", "id"):
            if candidate in df.columns:
                df = df.rename(columns={candidate: "cell_id"})
                break

        if "cell_id" not in df.columns:
            return [], "CSV must contain a 'cell_id' column (or similar)."

        df["cell_id"] = df["cell_id"].astype(str).str.strip()

        # This file is the list of SUSPECTED sites only — it must not carry any
        # verdict/probability columns. If the uploaded file happens to be a prior
        # report, drop those so the pipeline computes its own verdict downstream.
        drop = [c for c in df.columns if any(k in c for k in
                ("verdict", "prob", "label", "prediction", "score"))]
        df = df.drop(columns=drop, errors="ignore")

        if "tech" not in df.columns:
            df["tech"] = ""
        df["tech"] = df["tech"].astype(str).str.strip()

        records = df.to_dict("records")
        return records, f"Parsed {len(records)} suspected site(s) from CSV."
    except Exception as e:
        return [], f"Failed to parse CSV: {e}"
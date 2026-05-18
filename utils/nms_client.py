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

def fetch_kpi_data(
    cell_ids: List[str],
    progress_callback=None,
) -> Tuple[Dict[str, pd.DataFrame], List[str]]:
    """
    Fetch KPI data for all cells.

    Parameters
    ----------
    cell_ids         : list of cell ID strings extracted from the CSV
    progress_callback: optional callable(frac: float, label: str) for UI progress

    Returns
    -------
    kpi_data  : dict {cell_id -> DataFrame with columns [timestamp, availability, cs_traffic, ps_traffic]}
    log_lines : list of status strings
    """
    kpi_data  : Dict[str, pd.DataFrame] = {}
    log_lines : List[str] = []

    for i, cid in enumerate(cell_ids):
        if progress_callback:
            progress_callback((i + 1) / len(cell_ids), f"Fetching KPIs for {cid}…")

        if NMS_MOCK:
            df, msg = _fetch_mock(cid)
        else:
            df, msg = _fetch_real(cid)

        kpi_data[cid] = df
        log_lines.append(msg)

    return kpi_data, log_lines


# ─── Mock data generator ──────────────────────────────────────────────────────

# Rough fraction of cells that should be "sleeping" in mock data
_SLEEPING_PROBABILITY = 0.35


def _fetch_mock(cell_id: str) -> Tuple[pd.DataFrame, str]:
    """Generate realistic synthetic KPI data for demo purposes."""
    time.sleep(0.05)   # tiny delay to feel real

    rng     = random.Random(cell_id)   # deterministic per cell_id
    is_sleep = rng.random() < _SLEEPING_PROBABILITY

    periods = OBS_DAYS * 24            # hourly samples
    now     = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    timestamps = [now - timedelta(hours=periods - i) for i in range(periods)]

    availability = []
    cs_traffic   = []
    ps_traffic   = []

    # Base traffic shape: sinusoidal daily pattern
    for t in timestamps:
        hour = t.hour
        # Peak around 12:00, trough around 03:00
        daily_factor = 0.4 + 0.6 * abs((hour - 12) / 12)  # 0.4–1.0
        noise = rng.gauss(0, 0.05)

        avail = max(0.0, min(100.0, 97 + rng.gauss(0, 1.5)))

        if is_sleep:
            # Sleeping: availability stays high, traffic collapses
            sleep_start = periods // 3           # fault starts ~33% into window
            idx = timestamps.index(t)
            if idx >= sleep_start:
                cs  = max(0.0, rng.gauss(0.5, 0.4))          # near-zero
                ps  = max(0.0, rng.gauss(1.2, 0.8))
            else:
                cs  = max(0.0, rng.gauss(60, 8) * daily_factor + noise * 10)
                ps  = max(0.0, rng.gauss(800, 80) * daily_factor + noise * 100)
        else:
            cs  = max(0.0, rng.gauss(60, 8)  * daily_factor + noise * 10)
            ps  = max(0.0, rng.gauss(800, 80) * daily_factor + noise * 100)

        availability.append(round(avail, 2))
        cs_traffic.append(round(cs, 2))
        ps_traffic.append(round(ps, 2))

    df = pd.DataFrame({
        "timestamp":    timestamps,
        "availability": availability,
        "cs_traffic":   cs_traffic,
        "ps_traffic":   ps_traffic,
        "_is_sleeping": is_sleep,   # hidden ground truth (only in mock)
    })

    status = "MOCK-SLEEPING" if is_sleep else "MOCK-HEALTHY"
    return df, f"[{status}] {cell_id}: {periods} hourly records fetched."


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
        records = df.to_dict("records")
        return records, f"Parsed {len(records)} site(s) from CSV."
    except Exception as e:
        return [], f"Failed to parse CSV: {e}"
"""
pages/dashboard.py — Main SleepGuard Dashboard
================================================
Renders the full 5-step pipeline UI for authenticated users.
"""

import io
import time
from datetime import datetime
from typing import Optional

import pandas as pd
import streamlit as st

from utils.auth import get_user, logout
from utils.config import (
    EMAIL_SUBJECT_KEYWORD,
    NMS_MOCK,
    MODEL_MOCK,
    REPORT_RECIPIENT,
)
from utils.email_client import (
    connect_imap,
    fetch_sleeping_cell_email,
    send_report_email,
)
from utils.nms_client import parse_sites_csv, fetch_kpi_data
from utils.plotter import generate_all_plots
from models.classifier import classify_plots
from utils.reporter import build_report_csv, summarise


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _log(msg: str, level: str = "info"):
    ts  = datetime.utcnow().strftime("%H:%M:%S")
    css = {"info": "log-info", "warn": "log-warn", "err": "log-err"}.get(level, "log-info")
    st.session_state["pipeline_log"].append(
        f'<span class="{css}">[{ts}] {msg}</span>'
    )


def _render_log_box():
    lines = st.session_state.get("pipeline_log", [])
    if lines:
        content = "<br>".join(lines[-60:])   # last 60 lines
        st.markdown(
            f'<div class="log-box">{content}</div>',
            unsafe_allow_html=True,
        )


def _step_pill(n: int, label: str, current: int):
    done   = current > n
    active = current == n
    cls    = "done" if done else ("active" if active else "")
    icon   = "✓" if done else str(n)
    st.markdown(
        f'<span class="step-pill {cls}">{icon} {label}</span>',
        unsafe_allow_html=True,
    )


def _metric(label: str, value, suffix: str = ""):
    st.markdown(
        f'<div class="metric-card">'
        f'<div class="metric-value">{value}{suffix}</div>'
        f'<div class="metric-label">{label}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _badge(text: str, kind: str):
    st.markdown(
        f'<span class="badge badge-{kind}">{text}</span>',
        unsafe_allow_html=True,
    )


# ─── Sidebar ──────────────────────────────────────────────────────────────────

def _render_sidebar():
    user = get_user()
    st.sidebar.markdown(f"""
    <div style="padding:1rem 0 0.5rem;">
      <div style="font-family:var(--mono);font-size:1rem;color:var(--accent);">
        📡 SleepGuard
      </div>
      <div style="font-size:0.75rem;color:var(--muted);margin-top:0.1rem;">
        Network Operations Platform
      </div>
    </div>
    <hr style="border-color:var(--border);margin:0.5rem 0;">
    """, unsafe_allow_html=True)

    st.sidebar.markdown(f"""
    <div style="background:var(--surface2);border:1px solid var(--border);
                border-radius:6px;padding:0.8rem 1rem;margin-bottom:1rem;">
      <div style="font-size:0.72rem;color:var(--muted);text-transform:uppercase;
                  letter-spacing:0.08em;">Logged in as</div>
      <div style="font-weight:600;color:var(--text);margin-top:0.2rem;">
        {user.get('display_name','?')}
      </div>
      <div style="font-size:0.72rem;color:var(--muted);">{user.get('email','')}</div>
      <div style="font-size:0.7rem;color:var(--muted);margin-top:0.1rem;">
        Role: <span style="color:var(--accent);">{user.get('role','engineer')}</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    step = st.session_state.get("pipeline_step", 0)
    st.sidebar.markdown("**Pipeline Steps**")
    steps = [
        (1, "Email Setup"),
        (2, "Fetch Email"),
        (3, "KPI Retrieval"),
        (4, "Plots & Classify"),
        (5, "Report"),
    ]
    for n, label in steps:
        _step_pill(n, label, step)

    st.sidebar.markdown('<hr style="border-color:var(--border);">', unsafe_allow_html=True)

    # Mode indicators
    st.sidebar.markdown("**Mode flags**")
    for flag, label, on_col, off_col in [
        (NMS_MOCK,   "NMS",   "#ffd166", "#00e5a0"),
        (MODEL_MOCK, "Model", "#ffd166", "#00e5a0"),
    ]:
        mode  = "MOCK" if flag else "LIVE"
        color = on_col if flag else off_col
        st.sidebar.markdown(
            f'<span style="font-family:var(--mono);font-size:0.72rem;">'
            f'{label}: <span style="color:{color};">{mode}</span></span>',
            unsafe_allow_html=True,
        )

    st.sidebar.markdown('<hr style="border-color:var(--border);">', unsafe_allow_html=True)

    if st.sidebar.button("🚪 Sign Out", use_container_width=True):
        logout()

    if st.sidebar.button("🔄 Reset Pipeline", use_container_width=True):
        keys_to_clear = [
            "email_connected","email_credentials","fetched_email","parsed_sites",
            "kpi_data","plots","classifications","report_csv","report_sent",
            "pipeline_log","pipeline_step","run_ts",
        ]
        for k in keys_to_clear:
            st.session_state[k] = None if k not in (
                "email_connected","report_sent") else False
        st.session_state["pipeline_log"] = []
        st.session_state["pipeline_step"] = 0
        st.rerun()


# ─── Step 1 – Email setup ─────────────────────────────────────────────────────

def _render_step1():
    st.markdown("## Step 1 — Connect Email Account")
    st.markdown("""
    <div style="color:var(--muted);font-size:0.85rem;margin-bottom:1rem;">
    Connect your corporate email so SleepGuard can scan for the daily
    sleeping-cell alert email and retrieve the attached site list.
    </div>
    """, unsafe_allow_html=True)

    # Show connection status
    if st.session_state.get("email_connected"):
        creds = st.session_state.get("email_credentials", {})
        st.success(f"✅ Connected: **{creds.get('email_address','')}**")
        if st.button("Disconnect / Change Account"):
            st.session_state["email_connected"] = False
            st.session_state["email_credentials"] = {}
            st.rerun()
        return

    col_form, col_info = st.columns([1.4, 1])

    with col_form:
        with st.form("email_connect_form"):
            provider = st.selectbox(
                "Email Provider",
                ["Gmail", "Outlook / Microsoft 365"],
                help="Select your corporate email provider.",
            )
            email_addr = st.text_input(
                "Email Address",
                placeholder="you@company.com",
                help="Your full corporate email address.",
            )
            password = st.text_input(
                "App Password / OAuth Token",
                type="password",
                help=(
                    "For Gmail: create an App Password at myaccount.google.com → Security.\n"
                    "For Outlook: use your regular password or an app-specific password."
                ),
            )
            st.caption(
                "🔒 Credentials are stored only in session memory and "
                "never persisted to disk or logs."
            )
            submitted = st.form_submit_button("Connect →", use_container_width=True)

        if submitted:
            if not email_addr or not password:
                st.error("Please enter both email address and password.")
            else:
                prov_key = "gmail" if "Gmail" in provider else "outlook"
                # Monkey-patch provider before connecting
                import utils.config as cfg
                cfg.EMAIL_PROVIDER = prov_key

                with st.spinner("Connecting to mail server…"):
                    ok, msg = connect_imap(email_addr, password)

                if ok:
                    st.session_state["email_connected"]   = True
                    st.session_state["email_credentials"] = {
                        "email_address": email_addr,
                        "password":      password,
                        "provider":      prov_key,
                    }
                    st.session_state["pipeline_step"] = max(
                        st.session_state["pipeline_step"], 1
                    )
                    _log(f"Email connected: {email_addr}")
                    st.success(msg)
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error(msg)

    with col_info:
        st.markdown("""
        <div style="background:var(--surface2);border:1px solid var(--border);
                    border-radius:8px;padding:1.2rem;">
          <div style="font-family:var(--mono);font-size:0.8rem;color:var(--accent);
                      margin-bottom:0.8rem;">Setup Guide</div>
          <div style="font-size:0.78rem;color:var(--muted);line-height:1.7;">
            <b style="color:var(--text);">Gmail</b><br>
            1. Go to Google Account → Security<br>
            2. Enable 2-Step Verification<br>
            3. Create an <em>App Password</em> for "Mail"<br>
            4. Use that 16-char code as the password here<br><br>
            <b style="color:var(--text);">Outlook / M365</b><br>
            1. Use your regular M365 password, or<br>
            2. Ask your IT admin for an app password<br>
            3. IMAP must be enabled in Outlook settings
          </div>
        </div>
        """, unsafe_allow_html=True)

    # Demo bypass
    st.markdown('<hr class="h-line">', unsafe_allow_html=True)
    st.markdown("**Demo:** Skip email connection and use a synthetic CSV instead.")
    if st.button("🧪 Use Demo Mode (no real email needed)"):
        _activate_demo_email()
        st.rerun()


def _activate_demo_email():
    """Inject a synthetic email + CSV into session state for demo purposes."""
    demo_csv = (
        "cell_id,site_name,region,vendor\n"
        "CL001,Lagos_Island_1,SW,Ericsson\n"
        "CL002,Ikeja_North,NW,Huawei\n"
        "CL003,Victoria_Island_2,SE,Nokia\n"
        "CL004,Lekki_Phase1,SE,Ericsson\n"
        "CL005,Surulere_Central,SW,Huawei\n"
        "CL006,Apapa_Port,SW,Nokia\n"
        "CL007,Ikoyi_Heights,SE,Ericsson\n"
        "CL008,Yaba_Tech,NW,Huawei\n"
    ).encode()

    st.session_state["email_connected"]   = True
    st.session_state["email_credentials"] = {
        "email_address": "demo@sleepguard.local",
        "password":      "DEMO",
        "provider":      "gmail",
    }
    st.session_state["fetched_email"] = {
        "subject":   "Sleeping Cell Alert — Daily Report",
        "sender":    "noc-automation@telecom.ng",
        "date":      datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000"),
        "body":      "Please find attached the list of sites suspected of sleeping cell activity.",
        "csv_bytes": demo_csv,
        "csv_name":  "suspected_sites.csv",
    }
    sites, _ = parse_sites_csv(demo_csv)
    st.session_state["parsed_sites"]   = sites
    st.session_state["pipeline_step"]  = 2
    _log("Demo mode activated — synthetic site list loaded.")


# ─── Step 2 – Fetch email ─────────────────────────────────────────────────────

def _render_step2():
    st.markdown("## Step 2 — Fetch Sleeping-Cell Alert Email")
    st.markdown(f"""
    <div style="color:var(--muted);font-size:0.85rem;margin-bottom:1rem;">
    Scanning INBOX for the most recent email with subject containing
    <code style="color:var(--accent);">"{EMAIL_SUBJECT_KEYWORD}"</code>
    and extracting the attached CSV of suspected sites.
    </div>
    """, unsafe_allow_html=True)

    fetched = st.session_state.get("fetched_email")

    if fetched:
        # Already fetched — show summary
        st.success("✅ Email retrieved and CSV parsed.")
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown(f"""
            <div style="background:var(--surface2);border:1px solid var(--border);
                        border-radius:6px;padding:0.9rem;font-size:0.82rem;">
              <b style="color:var(--muted);">Subject:</b>
              <span style="color:var(--text);">{fetched['subject']}</span><br>
              <b style="color:var(--muted);">From:</b>
              <span style="color:var(--text);">{fetched['sender']}</span><br>
              <b style="color:var(--muted);">Date:</b>
              <span style="color:var(--text);">{fetched['date']}</span><br>
              <b style="color:var(--muted);">Attachment:</b>
              <span style="color:var(--accent);">{fetched.get('csv_name','(none)')}</span>
            </div>
            """, unsafe_allow_html=True)
        with col_b:
            sites = st.session_state.get("parsed_sites", [])
            _metric("Sites in List", len(sites))

        if sites:
            st.markdown("**Extracted site list:**")
            st.dataframe(pd.DataFrame(sites), use_container_width=True, height=200)

        st.button("↩ Re-fetch Email", on_click=lambda: st.session_state.update(
            fetched_email=None, parsed_sites=None))
        return

    # Not yet fetched
    col_btn, col_upload = st.columns([1, 1.4])

    with col_btn:
        keyword = st.text_input(
            "Subject keyword",
            value=EMAIL_SUBJECT_KEYWORD,
            help="Case-insensitive substring to match in email subject.",
        )
        if st.button("📥 Fetch from Inbox", use_container_width=True):
            creds = st.session_state.get("email_credentials", {})
            with st.spinner("Searching inbox…"):
                result, msg = fetch_sleeping_cell_email(
                    creds["email_address"],
                    creds["password"],
                    keyword=keyword,
                )
            if result is None:
                st.error(msg)
                _log(msg, "err")
            else:
                if result.get("csv_bytes") is None:
                    st.warning("Email found but no CSV attachment detected.")
                    _log("Email found but no CSV attachment.", "warn")
                else:
                    sites, parse_msg = parse_sites_csv(result["csv_bytes"])
                    st.session_state["fetched_email"] = result
                    st.session_state["parsed_sites"]  = sites
                    st.session_state["pipeline_step"] = max(
                        st.session_state["pipeline_step"], 2
                    )
                    _log(msg)
                    _log(parse_msg)
                    st.success(msg)
                    time.sleep(0.4)
                    st.rerun()

    with col_upload:
        st.markdown("**Or upload a CSV directly:**")
        uploaded = st.file_uploader(
            "Drop CSV here",
            type=["csv"],
            help="CSV must contain a 'cell_id' column.",
            label_visibility="collapsed",
        )
        if uploaded:
            csv_bytes = uploaded.read()
            sites, msg = parse_sites_csv(csv_bytes)
            if sites:
                st.session_state["fetched_email"] = {
                    "subject":   "Manual Upload",
                    "sender":    "(direct upload)",
                    "date":      datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000"),
                    "body":      "",
                    "csv_bytes": csv_bytes,
                    "csv_name":  uploaded.name,
                }
                st.session_state["parsed_sites"]  = sites
                st.session_state["pipeline_step"] = max(
                    st.session_state["pipeline_step"], 2
                )
                _log(f"CSV uploaded: {uploaded.name} — {len(sites)} sites.")
                st.success(msg)
                time.sleep(0.3)
                st.rerun()
            else:
                st.error(msg)


# ─── Step 3 – KPI retrieval ───────────────────────────────────────────────────

def _render_step3():
    st.markdown("## Step 3 — KPI Data Retrieval")
    st.markdown("""
    <div style="color:var(--muted);font-size:0.85rem;margin-bottom:1rem;">
    Querying the Network Management System for <code>availability</code>,
    <code>cs_traffic</code>, and <code>ps_traffic</code> for each suspected site
    over the observation window.
    </div>
    """, unsafe_allow_html=True)

    kpi_data = st.session_state.get("kpi_data")
    sites    = st.session_state.get("parsed_sites", [])

    if kpi_data:
        st.success(f"✅ KPI data retrieved for {len(kpi_data)} cells.")
        cell_ids = list(kpi_data.keys())
        sel = st.selectbox("Preview cell:", cell_ids)
        if sel:
            df = kpi_data[sel]
            st.line_chart(
                df.set_index("timestamp")[["availability", "cs_traffic", "ps_traffic"]],
                use_container_width=True,
                height=220,
            )
        st.button("↩ Re-fetch KPIs", on_click=lambda: st.session_state.update(kpi_data=None))
        return

    if not sites:
        st.warning("No sites available. Complete Step 2 first.")
        return

    nms_note = (
        "🟡 NMS is in **MOCK** mode — synthetic KPI data will be generated."
        if NMS_MOCK else
        "🟢 NMS is in **LIVE** mode — real API calls will be made."
    )
    st.info(nms_note)

    if st.button(f"⬇️ Fetch KPIs for {len(sites)} sites", use_container_width=True):
        progress_bar = st.progress(0.0)
        status_text  = st.empty()

        def _cb(frac, label):
            progress_bar.progress(frac)
            status_text.text(label)

        cell_ids = [s["cell_id"] for s in sites]
        kpi, logs = fetch_kpi_data(cell_ids, progress_callback=_cb)

        for l in logs:
            _log(l)

        st.session_state["kpi_data"]       = kpi
        st.session_state["pipeline_step"]  = max(st.session_state["pipeline_step"], 3)
        progress_bar.progress(1.0)
        status_text.text("Done.")
        time.sleep(0.3)
        st.rerun()


# ─── Step 4 – Plot generation & classification ────────────────────────────────

def _render_step4():
    st.markdown("## Step 4 — Plot Generation & Classification")
    st.markdown("""
    <div style="color:var(--muted);font-size:0.85rem;margin-bottom:1rem;">
    Generating diagnostic plots then running them through the ResNet vision model.
    </div>
    """, unsafe_allow_html=True)

    kpi_data        = st.session_state.get("kpi_data")
    plots           = st.session_state.get("plots")
    classifications = st.session_state.get("classifications")

    if not kpi_data:
        st.warning("KPI data not available. Complete Step 3 first.")
        return

    tab_run, tab_results = st.tabs(["Run Pipeline", "View Plots & Results"])

    with tab_run:
        model_note = (
            "🟡 **Model MOCK** — simulated classification (no PyTorch / weights required)."
            if MODEL_MOCK else
            "🟢 **Model LIVE** — ResNet inference running."
        )
        st.info(model_note)

        if classifications:
            summ = summarise(classifications)
            st.success(
                f"✅ Classification complete — "
                f"**{summ['sleeping']}** sleeping / **{summ['healthy']}** healthy "
                f"out of {summ['total']} cells."
            )
            if st.button("↩ Re-run classification"):
                st.session_state["plots"]           = None
                st.session_state["classifications"] = None
                st.rerun()
        else:
            if st.button("▶️ Generate Plots & Classify", use_container_width=True):
                # --- Plot generation ---
                st.markdown("**Generating plots…**")
                pb1 = st.progress(0.0)
                s1  = st.empty()

                def _pcb(f, l): pb1.progress(f); s1.text(l)

                new_plots, plot_logs = generate_all_plots(kpi_data, _pcb)
                for l in plot_logs: _log(l)
                pb1.progress(1.0); s1.text("Plots done.")

                # --- Classification ---
                st.markdown("**Running vision model…**")
                pb2 = st.progress(0.0)
                s2  = st.empty()

                def _ccb(f, l): pb2.progress(f); s2.text(l)

                new_cls, cls_logs = classify_plots(new_plots, _ccb)
                for l in cls_logs: _log(l)
                pb2.progress(1.0); s2.text("Classification done.")

                st.session_state["plots"]           = new_plots
                st.session_state["classifications"] = new_cls
                st.session_state["pipeline_step"]   = max(
                    st.session_state["pipeline_step"], 4
                )
                time.sleep(0.3)
                st.rerun()

    with tab_results:
        if not plots or not classifications:
            st.info("Run the pipeline first (← Run Pipeline tab).")
            return

        # Summary metrics
        summ = summarise(classifications)
        c1, c2, c3, c4 = st.columns(4)
        with c1: _metric("Total Sites", summ["total"])
        with c2: _metric("Sleeping", summ["sleeping"])
        with c3: _metric("Healthy", summ["healthy"])
        with c4: _metric("Fault Rate", summ["rate"], "%")

        st.markdown('<hr class="h-line">', unsafe_allow_html=True)

        # Per-cell explorer
        cell_ids = list(plots.keys())
        sel_cell = st.selectbox("Inspect cell:", cell_ids)

        if sel_cell:
            res = classifications[sel_cell]
            verdict = "SLEEPING" if res["final"] == 1 else "HEALTHY"
            badge_kind = "sleeping" if res["final"] == 1 else "healthy"

            col_badge, col_cs, col_ps = st.columns([1, 2, 2])
            with col_badge:
                st.markdown("**Verdict:**")
                _badge(verdict, badge_kind)
                st.markdown(f"""
                <div style="margin-top:0.8rem;font-size:0.78rem;color:var(--muted);">
                CS prob: <span style="color:var(--text);">{res['cs_prob']:.3f}</span><br>
                PS prob: <span style="color:var(--text);">{res['ps_prob']:.3f}</span>
                </div>
                """, unsafe_allow_html=True)

            with col_cs:
                st.markdown("**Availability vs CS Traffic**")
                st.image(
                    io.BytesIO(plots[sel_cell]["cs"]),
                    use_container_width=True,
                )
                label_cs = "Sleeping ⚠" if res["cs_label"] else "Healthy ✓"
                _badge(f"CS: {label_cs}", "sleeping" if res["cs_label"] else "healthy")

            with col_ps:
                st.markdown("**Availability vs PS Traffic**")
                st.image(
                    io.BytesIO(plots[sel_cell]["ps"]),
                    use_container_width=True,
                )
                label_ps = "Sleeping ⚠" if res["ps_label"] else "Healthy ✓"
                _badge(f"PS: {label_ps}", "sleeping" if res["ps_label"] else "healthy")

        # Full results table
        st.markdown("---")
        st.markdown("**All Classifications**")
        table_rows = []
        for cid, r in classifications.items():
            table_rows.append({
                "Cell ID":    cid,
                "CS Prob":    f"{r['cs_prob']:.3f}",
                "PS Prob":    f"{r['ps_prob']:.3f}",
                "CS Label":   "Sleeping" if r["cs_label"] else "Healthy",
                "PS Label":   "Sleeping" if r["ps_label"] else "Healthy",
                "Final":      "🔴 SLEEPING" if r["final"] else "🟢 Healthy",
            })
        st.dataframe(pd.DataFrame(table_rows), use_container_width=True)


# ─── Step 5 – Report & send ───────────────────────────────────────────────────

def _render_step5():
    st.markdown("## Step 5 — Report Generation & Delivery")
    st.markdown("""
    <div style="color:var(--muted);font-size:0.85rem;margin-bottom:1rem;">
    Compile confirmed sleeping cells into a CSV and dispatch to the NOC team.
    </div>
    """, unsafe_allow_html=True)

    classifications = st.session_state.get("classifications")
    sites           = st.session_state.get("parsed_sites", [])

    if not classifications:
        st.warning("No classification results available. Complete Step 4 first.")
        return

    summ = summarise(classifications)

    # Build / cache report CSV
    if not st.session_state.get("report_csv"):
        st.session_state["report_csv"] = build_report_csv(classifications, sites)

    report_bytes = st.session_state["report_csv"]

    col_summ, col_actions = st.columns([1.2, 1])

    with col_summ:
        st.markdown("### Summary")
        c1, c2 = st.columns(2)
        with c1: _metric("Sleeping Cells", summ["sleeping"])
        with c2: _metric("Fault Rate", summ["rate"], "%")

        st.markdown("**Confirmed sleeping cells:**")
        sleeping_ids = [cid for cid, r in classifications.items() if r["final"] == 1]
        if sleeping_ids:
            for cid in sleeping_ids:
                r = classifications[cid]
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:0.6rem;'
                    f'margin-bottom:0.4rem;">'
                    f'<span class="badge badge-sleeping">SLEEPING</span>'
                    f'<span style="font-family:var(--mono);font-size:0.82rem;">{cid}</span>'
                    f'<span style="color:var(--muted);font-size:0.75rem;">'
                    f'CS={r["cs_prob"]:.2f} PS={r["ps_prob"]:.2f}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.success("✅ No sleeping cells detected in this batch.")

    with col_actions:
        st.markdown("### Actions")

        # Download
        st.download_button(
            label="⬇️ Download Report CSV",
            data=report_bytes,
            file_name="sleeping_cells_report.csv",
            mime="text/csv",
            use_container_width=True,
        )

        st.markdown('<hr class="h-line">', unsafe_allow_html=True)

        # Email send
        if not summ["sleeping"]:
            st.info("No sleeping cells to report — email dispatch skipped.")
        elif st.session_state.get("report_sent"):
            st.success("✅ Report already sent this session.")
        else:
            creds = st.session_state.get("email_credentials", {})
            recipient = st.text_input("Send report to:", value=REPORT_RECIPIENT)

            if st.button("📧 Send Report Email", use_container_width=True):
                if not creds.get("email_address") or creds.get("provider") == "demo":
                    st.warning("Demo mode — email send skipped (no real SMTP credentials).")
                    _log("Demo: email send simulated.", "warn")
                    st.session_state["report_sent"] = True
                else:
                    with st.spinner("Sending…"):
                        ok, msg = send_report_email(
                            sender_address=creds["email_address"],
                            sender_password=creds["password"],
                            recipient=recipient,
                            csv_bytes=report_bytes,
                            extra_body=f"{summ['sleeping']} sleeping cell(s) confirmed.",
                        )
                    if ok:
                        st.success(msg)
                        st.session_state["report_sent"] = True
                        _log(msg)
                    else:
                        st.error(msg)
                        _log(msg, "err")


# ─── Main dashboard renderer ──────────────────────────────────────────────────

def render_dashboard():
    _render_sidebar()

    user = get_user()

    # Hero banner
    run_ts = st.session_state.get("run_ts") or datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    st.markdown(f"""
    <div class="hero-banner">
      <div class="hero-title">SleepGuard</div>
      <div class="hero-sub">
        Automated Sleeping Cell Detection &nbsp;·&nbsp;
        {user.get('display_name','')} &nbsp;·&nbsp; {run_ts}
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Overall progress
    step = st.session_state.get("pipeline_step", 0)
    st.progress(min(step / 5, 1.0))
    st.caption(f"Pipeline progress: {step}/5 steps complete")

    st.markdown('<hr class="h-line">', unsafe_allow_html=True)

    # Render active step
    # Always show all steps as expandable panels, active one pre-expanded

    # Step 1
    with st.expander("**Step 1 — Email Account Setup**",
                     expanded=(step < 1 or not st.session_state.get("email_connected"))):
        _render_step1()

    if not st.session_state.get("email_connected"):
        st.info("Complete Step 1 to unlock the rest of the pipeline.")
        return

    # Step 2
    with st.expander("**Step 2 — Fetch Alert Email**",
                     expanded=(step == 1 or not st.session_state.get("parsed_sites"))):
        _render_step2()

    if not st.session_state.get("parsed_sites"):
        return

    # Step 3
    with st.expander("**Step 3 — KPI Data Retrieval**",
                     expanded=(step == 2 or not st.session_state.get("kpi_data"))):
        _render_step3()

    if not st.session_state.get("kpi_data"):
        return

    # Step 4
    with st.expander("**Step 4 — Plots & Classification**",
                     expanded=(step == 3 or not st.session_state.get("classifications"))):
        _render_step4()

    if not st.session_state.get("classifications"):
        return

    # Step 5
    with st.expander("**Step 5 — Report & Delivery**", expanded=True):
        _render_step5()

    # System log
    st.markdown('<hr class="h-line">', unsafe_allow_html=True)
    with st.expander("🖥 System Log"):
        _render_log_box()
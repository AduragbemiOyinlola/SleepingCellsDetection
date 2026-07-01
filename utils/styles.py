"""
utils/styles.py — Global CSS injection for SleepGuard UI
"""
import streamlit as st


GLOBAL_CSS = """
<style>
/* ── Fonts ──────────────────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');

/* ── Root palette ────────────────────────────────────────────────────────── */
:root {
  --bg:         #0b0f1a;
  --surface:    #111827;
  --surface2:   #1a2233;
  --border:     #1f2d42;
  --accent:     #00d4ff;
  --accent2:    #ff6b35;
  --success:    #00e5a0;
  --warning:    #ffd166;
  --danger:     #ff4757;
  --text:       #e2e8f0;
  --muted:      #64748b;
  --mono:       'Space Mono', monospace;
  --sans:       'DM Sans', sans-serif;
}

/* ── Base ────────────────────────────────────────────────────────────────── */
html, body, [class*="css"] {
  background-color: var(--bg) !important;
  color: var(--text) !important;
  font-family: var(--sans) !important;
}

/* ── Sidebar ─────────────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
  background: var(--surface) !important;
  border-right: 1px solid var(--border) !important;
}
section[data-testid="stSidebar"] * { font-family: var(--sans) !important; }

/* ── Headers ─────────────────────────────────────────────────────────────── */
h1, h2, h3 {
  font-family: var(--mono) !important;
  letter-spacing: -0.02em;
}
h1 { color: var(--accent) !important; }
h2 { color: var(--text) !important; }

/* ── Buttons ─────────────────────────────────────────────────────────────── */
.stButton > button {
  background: linear-gradient(135deg, var(--accent), #0099cc) !important;
  color: #000 !important;
  font-family: var(--mono) !important;
  font-weight: 700 !important;
  font-size: 0.82rem !important;
  letter-spacing: 0.05em !important;
  border: none !important;
  border-radius: 4px !important;
  padding: 0.55rem 1.4rem !important;
  transition: all 0.2s ease !important;
  text-transform: uppercase !important;
}
.stButton > button:hover {
  filter: brightness(1.15) !important;
  transform: translateY(-1px) !important;
  box-shadow: 0 6px 20px rgba(0,212,255,0.35) !important;
}
.stButton > button:active { transform: translateY(0) !important; }

/* Secondary button override via class */
.btn-secondary > button {
  background: var(--surface2) !important;
  color: var(--accent) !important;
  border: 1px solid var(--border) !important;
}

/* ── Inputs ──────────────────────────────────────────────────────────────── */
input, textarea, select, [data-baseweb="input"] input {
  background: var(--surface2) !important;
  color: var(--text) !important;
  border: 1px solid var(--border) !important;
  border-radius: 4px !important;
  font-family: var(--sans) !important;
}
input:focus { border-color: var(--accent) !important; outline: none !important; }

/* ── Cards / metric boxes ────────────────────────────────────────────────── */
.metric-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1.2rem 1.4rem;
  position: relative;
  overflow: hidden;
}
.metric-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: linear-gradient(90deg, var(--accent), transparent);
}
.metric-value {
  font-family: var(--mono);
  font-size: 2rem;
  font-weight: 700;
  color: var(--accent);
  line-height: 1;
}
.metric-label {
  font-size: 0.75rem;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin-top: 0.3rem;
}

/* ── Status badges ───────────────────────────────────────────────────────── */
.badge {
  display: inline-block;
  padding: 0.2rem 0.6rem;
  border-radius: 3px;
  font-family: var(--mono);
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.badge-sleeping  { background: rgba(255,71,87,0.18);  color: var(--danger);  border: 1px solid rgba(255,71,87,0.4); }
.badge-healthy   { background: rgba(0,229,160,0.12);  color: var(--success); border: 1px solid rgba(0,229,160,0.3); }
.badge-pending   { background: rgba(255,209,102,0.12);color: var(--warning); border: 1px solid rgba(255,209,102,0.3);}

/* ── Progress bar ────────────────────────────────────────────────────────── */
.stProgress > div > div { background: var(--accent) !important; }

/* ── Dataframe / table ───────────────────────────────────────────────────── */
.stDataFrame { border: 1px solid var(--border) !important; border-radius: 6px !important; }
.stDataFrame thead { background: var(--surface2) !important; }

/* ── Expander ────────────────────────────────────────────────────────────── */
.streamlit-expanderHeader {
  background: var(--surface2) !important;
  border: 1px solid var(--border) !important;
  border-radius: 6px !important;
  font-family: var(--mono) !important;
  font-size: 0.82rem !important;
}

/* ── Log terminal ────────────────────────────────────────────────────────── */
.log-box {
  background: #050810;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 1rem;
  font-family: var(--mono);
  font-size: 0.75rem;
  color: #7dffb3;
  max-height: 240px;
  overflow-y: auto;
  line-height: 1.6;
}
.log-box .log-err  { color: var(--danger); }
.log-box .log-warn { color: var(--warning); }
.log-box .log-info { color: #7dffb3; }

/* ── Hero banner ─────────────────────────────────────────────────────────── */
.hero-banner {
  background: linear-gradient(135deg, #0b0f1a 0%, #0f1f33 50%, #0b0f1a 100%);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 2rem 2.4rem;
  margin-bottom: 1.5rem;
  position: relative;
  overflow: hidden;
}
.hero-banner::after {
  content: '📡';
  position: absolute;
  right: 2rem; top: 50%;
  transform: translateY(-50%);
  font-size: 4rem;
  opacity: 0.08;
}
.hero-title {
  font-family: var(--mono);
  font-size: 1.6rem;
  color: var(--accent);
  margin: 0 0 0.3rem 0;
}
.hero-sub {
  font-size: 0.9rem;
  color: var(--muted);
  margin: 0;
}

/* ── Step pill ───────────────────────────────────────────────────────────── */
.step-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 0.3rem 0.8rem;
  font-family: var(--mono);
  font-size: 0.72rem;
  color: var(--muted);
  margin-bottom: 0.8rem;
}
.step-pill.active { border-color: var(--accent); color: var(--accent); }
.step-pill.done   { border-color: var(--success); color: var(--success); }

/* ── Divider ─────────────────────────────────────────────────────────────── */
.h-line {
  border: none;
  border-top: 1px solid var(--border);
  margin: 1.2rem 0;
}

/* ── Misc Streamlit overrides ────────────────────────────────────────────── */
.stAlert { border-radius: 6px !important; }
[data-testid="stMetric"] { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; }
[data-testid="stMetricLabel"] { color: var(--muted) !important; font-size: 0.75rem !important; text-transform: uppercase; letter-spacing: 0.08em; }
[data-testid="stMetricValue"] { color: var(--accent) !important; font-family: var(--mono) !important; }

/* ── File uploader ───────────────────────────────────────────────────────── */
[data-testid="stFileUploader"] {
  background: var(--surface2) !important;
  border: 1px dashed var(--border) !important;
  border-radius: 6px !important;
}

/* ── Tabs ────────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] { background: var(--surface) !important; border-bottom: 1px solid var(--border) !important; }
.stTabs [data-baseweb="tab"] { font-family: var(--mono) !important; font-size: 0.78rem !important; color: var(--muted) !important; }
.stTabs [aria-selected="true"] { color: var(--accent) !important; border-bottom: 2px solid var(--accent) !important; }

/* ── Hide Streamlit's automatic multipage nav (the "app"/"dashboard" list) ── */
[data-testid="stSidebarNav"] { display: none !important; }

/* ── Custom sidebar ──────────────────────────────────────────────────────── */
.sb-brand { padding: 0.4rem 0 0.2rem; }
.sb-logo { font-family: var(--mono); font-size: 1.05rem; color: var(--accent); }
.sb-tagline { font-size: 0.72rem; color: var(--muted); margin-top: 0.1rem; }
.sb-nav {
  display: flex; align-items: center; gap: 0.55rem;
  margin: 0.9rem 0 0.4rem; padding: 0.55rem 0.8rem;
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
  border-radius: 9px; color: var(--text); font-weight: 600; font-size: 0.9rem;
}
.sb-nav-icon { font-size: 1rem; }
.sb-user {
  background: var(--surface2); border: 1px solid var(--border);
  border-radius: 10px; padding: 0.8rem 1rem; margin: 0.8rem 0 1rem;
}
.sb-user-label { font-size: 0.66rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.09em; }
.sb-user-name { font-weight: 600; color: var(--text); margin-top: 0.2rem; }
.sb-user-mail { font-size: 0.72rem; color: var(--muted); word-break: break-all; }
.sb-user-role { font-size: 0.7rem; color: var(--muted); margin-top: 0.15rem; }
.sb-user-role span { color: var(--accent); }
.sb-section { font-size: 0.68rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.12em; margin: 0.3rem 0 0.6rem; }
.sb-step {
  display: flex; align-items: center; gap: 0.6rem;
  padding: 0.45rem 0.7rem; margin-bottom: 0.4rem; border-radius: 8px;
  font-size: 0.82rem; color: var(--muted);
  border: 1px solid transparent;
}
.sb-step .sb-step-n {
  width: 22px; height: 22px; border-radius: 50%; flex: 0 0 22px;
  display: inline-flex; align-items: center; justify-content: center;
  font-family: var(--mono); font-size: 0.72rem;
  background: var(--surface2); border: 1px solid var(--border); color: var(--muted);
}
.sb-step.active { background: color-mix(in srgb, var(--accent) 12%, transparent); color: var(--text); border-color: color-mix(in srgb, var(--accent) 40%, transparent); }
.sb-step.active .sb-step-n { background: var(--accent); color: #00131c; border-color: var(--accent); }
.sb-step.done { color: var(--text); }
.sb-step.done .sb-step-n { background: var(--success); color: #00131c; border-color: var(--success); }
.sb-divider { border-top: 1px solid var(--border); margin: 1rem 0; }

/* account chip + icon sign-out (bottom of sidebar) */
.sb-acct { display: flex; align-items: center; gap: 0.6rem; padding: 0.2rem 0; }
.sb-avatar {
  width: 36px; height: 36px; flex: 0 0 36px; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center;
  font-family: var(--mono); font-weight: 700; font-size: 0.9rem;
  color: var(--accent); background: color-mix(in srgb, var(--accent) 16%, transparent);
  border: 2px solid color-mix(in srgb, var(--accent) 55%, transparent);
}
.sb-acct-name { font-weight: 600; color: var(--text); font-size: 0.9rem; line-height: 1.1; }
.sb-acct-role { font-size: 0.66rem; letter-spacing: 0.12em; color: var(--muted); text-transform: uppercase; }
/* make the keyed sign-out button an icon-only control */
.st-key-signout_btn button {
  background: transparent !important; border: 1px solid var(--border) !important;
  box-shadow: none !important; padding: 0.4rem !important; min-height: 0 !important;
  font-size: 0 !important; color: transparent !important; line-height: 0 !important;
}
.st-key-signout_btn button p,
.st-key-signout_btn button div,
.st-key-signout_btn button span { display: none !important; }   /* hide the "logout" text */
.st-key-signout_btn button::before {
  content: ''; display: inline-block; width: 18px; height: 18px;
  background-color: var(--muted);
  -webkit-mask: url("data:image/svg+xml,%3Csvg%20xmlns%3D%27http%3A//www.w3.org/2000/svg%27%20viewBox%3D%270%200%2024%2024%27%20fill%3D%27none%27%20stroke%3D%27black%27%20stroke-width%3D%272%27%20stroke-linecap%3D%27round%27%20stroke-linejoin%3D%27round%27%3E%3Cpath%20d%3D%27M9%2021H5a2%202%200%200%201-2-2V5a2%202%200%200%201%202-2h4%27/%3E%3Cpolyline%20points%3D%2716%2017%2021%2012%2016%207%27/%3E%3Cline%20x1%3D%2721%27%20y1%3D%2712%27%20x2%3D%279%27%20y2%3D%2712%27/%3E%3C/svg%3E") center/contain no-repeat;
  mask: url("data:image/svg+xml,%3Csvg%20xmlns%3D%27http%3A//www.w3.org/2000/svg%27%20viewBox%3D%270%200%2024%2024%27%20fill%3D%27none%27%20stroke%3D%27black%27%20stroke-width%3D%272%27%20stroke-linecap%3D%27round%27%20stroke-linejoin%3D%27round%27%3E%3Cpath%20d%3D%27M9%2021H5a2%202%200%200%201-2-2V5a2%202%200%200%201%202-2h4%27/%3E%3Cpolyline%20points%3D%2716%2017%2021%2012%2016%207%27/%3E%3Cline%20x1%3D%2721%27%20y1%3D%2712%27%20x2%3D%279%27%20y2%3D%2712%27/%3E%3C/svg%3E") center/contain no-repeat;
}
.st-key-signout_btn button:hover { border-color: var(--accent) !important; transform: none !important; }
.st-key-signout_btn button:hover::before { background-color: var(--accent); }

/* sun/moon theme switch (keyed button; knob gradient injected per-theme) */
.st-key-theme_btn button {
  width: 58px !important; height: 28px !important; min-height: 0 !important;
  border-radius: 999px !important; padding: 0 !important;
  border: 1px solid var(--border) !important; box-shadow: none !important;
  font-size: 0 !important; position: relative; overflow: hidden;
}
.st-key-theme_btn button:hover { transform: none !important; filter: none !important; }
.st-key-theme_btn button p,
.st-key-theme_btn button div,
.st-key-theme_btn button span { display: none !important; }
.st-key-theme_btn button::before {
  content: '☀'; position: absolute; left: 7px; top: 50%; transform: translateY(-50%);
  font-size: 12px; line-height: 1; }
.st-key-theme_btn button::after {
  content: '🌙'; position: absolute; right: 7px; top: 50%; transform: translateY(-50%);
  font-size: 11px; line-height: 1; }
.sb-theme-label { font-size: 0.88rem; color: var(--text); padding-top: 4px; }

/* download / form-submit buttons share the primary button look (fixes
   invisible text in light mode where they otherwise fall back to defaults) */
[data-testid="stDownloadButton"] > button,
[data-testid="stFormSubmitButton"] > button {
  background: linear-gradient(135deg, var(--accent), #0099cc) !important;
  color: #00131c !important; font-family: var(--mono) !important;
  font-weight: 700 !important; text-transform: uppercase !important;
  border: none !important; border-radius: 4px !important; letter-spacing: 0.05em !important;
}

/* pin the theme switch + account chip to the very bottom of the sidebar.
   Streamlit wraps every widget in element-container > stVerticalBlock, so
   flex-grow on a nested wrapper does NOT propagate. Instead we make the
   sidebar's content column full-height and give the spacer's container
   margin-top:auto, which pushes it and everything after it to the bottom. */
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"],
section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
  min-height: calc(100vh - 2rem);
}
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > [data-testid="stVerticalBlock"],
section[data-testid="stSidebar"] [data-testid="stSidebarContent"] > [data-testid="stVerticalBlock"] {
  min-height: calc(100vh - 2rem);
  display: flex; flex-direction: column;
}
section[data-testid="stSidebar"] [data-testid="element-container"]:has(.sb-spacer) {
  margin-top: auto !important;
}
.sb-spacer { height: 0; }
</style>
"""


# Light-mode palette override (re-declares :root after the base CSS, so it wins).
LIGHT_OVERRIDE = """
<style>
:root {
  --bg:       #eef3f9;
  --surface:  #ffffff;
  --surface2: #f1f5fb;
  --border:   #d6e0ec;
  --accent:   #0091d6;
  --accent2:  #e2680c;
  --success:  #07a878;
  --warning:  #b9820a;
  --danger:   #e23d4d;
  --text:     #0f1b2d;
  --muted:    #5a6b80;
}
html, body, [class*="css"] { background-color: var(--bg) !important; color: var(--text) !important; }
[data-testid="stAppViewContainer"] { background: var(--bg) !important; }
[data-baseweb="select"] > div { background: var(--surface2) !important; }
/* selected value + dropdown option text must be dark in light mode (was near-white) */
[data-baseweb="select"], [data-baseweb="select"] * { color: var(--text) !important; }
[data-baseweb="select"] svg { fill: var(--muted) !important; color: var(--muted) !important; }
[data-baseweb="popover"], [data-baseweb="menu"], [role="listbox"] { background: var(--surface) !important; }
[data-baseweb="popover"] [role="option"], [role="listbox"] [role="option"],
[role="listbox"] * { color: var(--text) !important; }
[role="option"]:hover { background: var(--surface2) !important; }

/* Modern Streamlit uses st-emotion-cache-* (not css-*), so force readable text
   on the actual content elements. Headings/accent spans keep their own colours. */
.stApp { color: var(--text); }
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] strong,
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary p,
[data-testid="stExpander"] summary span,
[data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] *,
.stCheckbox label, .stRadio label, .stSelectbox label, .stTextInput label,
label {
  color: var(--text) !important;
}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * {
  color: var(--muted) !important;
}
/* Expander shell + chevron */
[data-testid="stExpander"] {
  background: var(--surface) !important;
  border: 1px solid var(--border) !important; border-radius: 10px !important;
}
[data-testid="stExpander"] summary svg { fill: var(--muted) !important; color: var(--muted) !important; }
/* Progress track */
[data-testid="stProgress"] > div > div { background: var(--surface2) !important; }
</style>
"""


def inject_global_styles():
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
    if st.session_state.get("theme", "dark") == "light":
        st.markdown(LIGHT_OVERRIDE, unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════════════
# Login page — centered composition over the network background
# ═════════════════════════════════════════════════════════════════════════════
from pathlib import Path

LOGIN_CSS_TEMPLATE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Saira:wght@300;400;500;600;700&display=swap');

/* hide Streamlit chrome on the login screen only */
header[data-testid="stHeader"], #MainMenu, footer { display: none !important; }
section[data-testid="stSidebar"] { display: none !important; }
[data-testid="collapsedControl"], [data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarCollapseButton"], [data-testid="stToolbar"],
button[kind="header"] { display: none !important; }

/* full-bleed network background (user image) with a gentle scrim for legibility */
[data-testid="stAppViewContainer"] > .main { background: transparent !important; }
[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(900px 520px at 50% 60%, rgba(4,8,16,0.55), transparent 70%),
    linear-gradient(180deg, rgba(7,11,20,0.30) 0%, rgba(7,11,20,0.15) 45%, rgba(7,11,20,0.55) 100%),
    url('data:image/jpeg;base64,__BG__') center/cover fixed no-repeat,
    #070b14 !important;
}
.block-container {
  max-width: 1200px !important;
  padding-top: 12vh !important; padding-bottom: 6vh !important;
  position: relative; z-index: 2;
}

/* hero (left, vertically centered) */
.login-hero { text-align: left; margin-bottom: 0; }
.login-mark {
  font-size: .74rem; font-family: var(--mono); letter-spacing: .42em;
  text-transform: uppercase; color: var(--accent);
  display: inline-flex; align-items: center; gap: .55rem; margin-bottom: 1.1rem;
}
.login-mark::after {
  content: ''; width: 34px; height: 1px;
  background: linear-gradient(90deg, var(--accent), transparent);
}
.login-brand {
  font-family: 'Saira', sans-serif; font-weight: 600;
  font-size: clamp(3rem, 6.2vw, 5rem); line-height: 1.02; margin: 0;
  color: #ffffff; letter-spacing: .005em;
  text-shadow: 0 0 46px rgba(0,196,255,.45), 0 4px 34px rgba(0,0,0,.55);
}
.login-tag {
  font-family: var(--sans); font-weight: 300; font-size: 1.12rem;
  color: #d6e6f4; max-width: 32ch; margin: 1rem 0 0; line-height: 1.55;
}

/* sign-in card (centered) — style the column holding .login-anchor */
[data-testid="stColumn"]:has(.login-anchor),
[data-testid="column"]:has(.login-anchor) {
  background: rgba(8,14,26,.55); backdrop-filter: blur(16px) saturate(1.1);
  border: 1px solid rgba(120,200,255,.18); border-radius: 18px;
  padding: 2.2rem 2rem 2.4rem !important; position: relative; z-index: 3;
  box-shadow: 0 30px 80px rgba(0,0,0,.5), inset 0 1px 0 rgba(255,255,255,.06);
}
.login-card-title {
  font-family: 'Saira', sans-serif; font-weight: 600; font-size: 1.5rem;
  color: #ffffff; margin: 0 0 1.4rem 0; line-height: 1.25; text-align: left;
}
.login-label {
  font-family: var(--mono); font-size: .68rem; letter-spacing: .18em;
  text-transform: uppercase; color: #9fb6cc; margin: 0 0 .4rem 0;
}

/* inputs + button inside the card */
[data-testid="stColumn"]:has(.login-anchor) input {
  background: rgba(255,255,255,.06) !important;
  border: 1px solid rgba(150,200,240,.22) !important;
  color: #fff !important; padding: .8rem .95rem !important; font-size: .96rem !important;
  border-radius: 10px !important;
}
[data-testid="stColumn"]:has(.login-anchor) input::placeholder { color: #7e93a8 !important; }
[data-testid="stColumn"]:has(.login-anchor) input:focus {
  border-color: var(--accent) !important; box-shadow: 0 0 0 3px rgba(0,212,255,.15) !important;
}
[data-testid="stColumn"]:has(.login-anchor) .stButton > button {
  width: 100%; margin-top: .9rem; padding: .82rem !important;
  border-radius: 10px !important; font-size: .82rem !important;
  background: linear-gradient(135deg, #18e0ff, #0091d6) !important;
  box-shadow: 0 10px 30px rgba(0,180,235,.35) !important;
}

/* responsive */
@media (max-width: 720px) {
  .block-container { padding-top: 4vh !important; max-width: 92% !important; }
  .login-brand { font-size: clamp(2.4rem, 11vw, 3.2rem); }
}
</style>
"""


def _login_bg_b64() -> str:
    try:
        return (Path(__file__).parent / "_login_bg.b64").read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def inject_login_styles():
    st.markdown(LOGIN_CSS_TEMPLATE.replace("__BG__", _login_bg_b64()),
                unsafe_allow_html=True)
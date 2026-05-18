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
</style>
"""


def inject_global_styles():
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
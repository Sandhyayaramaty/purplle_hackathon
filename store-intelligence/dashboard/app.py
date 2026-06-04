"""
Store Intelligence Dashboard  ·  Enhanced UI Edition
Streamlit app — reads directly from DuckDB for speed.
Run: streamlit run dashboard/app.py
"""

import os
import sys
import json
import duckdb
import subprocess
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from api.analytics import (
    footfall_summary, hourly_footfall, demographic_breakdown,
    zone_heatmap, zone_conversion, queue_stats,
    revenue_summary, top_brands, revenue_by_hour,
    detect_anomalies,
)

BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = str(
    BASE_DIR.parent / "Data" / "store_intelligence.db"
)

print("DB_PATH =", DB_PATH)
print("Exists =", Path(DB_PATH).exists())

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Store Intelligence",
    page_icon="🏪",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Design System ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&family=Figtree:ital,wght@0,300;0,400;0,500;0,600;1,300;1,400&family=JetBrains+Mono:wght@400;500&display=swap');

/* ─── Tokens ─────────────────────────────────────────────────── */
:root {
    --void:          #080b14;
    --base:          #0d1221;
    --surface:       #111829;
    --raised:        #16202f;
    --overlay:       #1c2a3d;

    --border-faint:  rgba(148,163,184,0.06);
    --border-subtle: rgba(148,163,184,0.11);
    --border-mid:    rgba(148,163,184,0.18);
    --border-bright: rgba(148,163,184,0.28);

    --gold:   #f0a500;
    --gold-d: #c77d00;
    --gold-l: #ffd166;
    --iris:   #7c83f5;
    --iris-d: #5b64e0;
    --iris-l: #a5aeff;
    --jade:   #00c49a;
    --jade-d: #009070;
    --jade-l: #4ee8c2;
    --rose:   #f0526e;
    --rose-d: #c23050;
    --rose-l: #fca5b5;
    --sky:    #38b9f0;
    --sky-l:  #90d8f7;

    --ink-1:  #f1f5f9;
    --ink-2:  #94a3b8;
    --ink-3:  #475569;
    --ink-4:  #2d3a4e;

    --r-sm: 8px;
    --r-md: 14px;
    --r-lg: 20px;
    --r-xl: 28px;

    --shadow-sm:  0 2px 8px rgba(0,0,0,0.3);
    --shadow-md:  0 4px 20px rgba(0,0,0,0.4);
    --shadow-lg:  0 8px 40px rgba(0,0,0,0.5);
    --glow-gold:  0 0 40px rgba(240,165,0,0.15);
    --glow-iris:  0 0 40px rgba(124,131,245,0.15);
}

/* ─── Global ─────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; }

html, body, [class*="css"] {
    font-family: 'Figtree', system-ui, sans-serif !important;
    color: var(--ink-1) !important;
}

.stApp {
    background: var(--void) !important;
    background-image:
        radial-gradient(ellipse 90% 60% at 15% -5%,  rgba(124,131,245,0.07) 0%, transparent 65%),
        radial-gradient(ellipse 70% 50% at 85% 100%, rgba(240,165,0,0.06)   0%, transparent 55%),
        radial-gradient(ellipse 50% 40% at 50% 50%,  rgba(0,196,154,0.03)   0%, transparent 60%) !important;
}

.block-container {
    padding: 1.5rem 2.25rem 3rem !important;
    max-width: 1680px !important;
}

/* ─── Sidebar ────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: var(--base) !important;
    border-right: 1px solid var(--border-faint) !important;
    width: 270px !important;
}

section[data-testid="stSidebar"] > div {
    padding: 0 !important;
}

/* ─── Typography ─────────────────────────────────────────────── */
h1, h2, h3, h4, h5, h6 {
    font-family: 'Outfit', sans-serif !important;
    letter-spacing: -0.025em !important;
}

h1 {
    font-size: 2.1rem !important;
    font-weight: 800 !important;
    background: linear-gradient(120deg, var(--ink-1) 40%, var(--gold-l)) !important;
    -webkit-background-clip: text !important;
    -webkit-text-fill-color: transparent !important;
    background-clip: text !important;
    line-height: 1.1 !important;
    margin-bottom: 0 !important;
}

h2 {
    font-size: 1.3rem !important;
    font-weight: 700 !important;
}

h3 {
    font-family: 'Figtree', sans-serif !important;
    font-size: 0.72rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.12em !important;
    text-transform: uppercase !important;
    color: var(--ink-3) !important;
}

/* ─── KPI Metric Cards ───────────────────────────────────────── */
div[data-testid="metric-container"] {
    background: var(--raised) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--r-md) !important;
    padding: 22px 20px 18px !important;
    box-shadow: var(--shadow-sm) !important;
    position: relative !important;
    overflow: hidden !important;
    transition: all 0.22s cubic-bezier(0.4,0,0.2,1) !important;
}

div[data-testid="metric-container"]::after {
    content: '' !important;
    position: absolute !important;
    inset: 0 !important;
    border-radius: inherit !important;
    background: linear-gradient(135deg,
        rgba(255,255,255,0.035) 0%,
        rgba(255,255,255,0)     60%) !important;
    pointer-events: none !important;
}

div[data-testid="metric-container"]::before {
    content: '' !important;
    position: absolute !important;
    top: 0; left: 0; right: 0 !important;
    height: 1.5px !important;
    background: linear-gradient(90deg,
        transparent,
        var(--gold) 40%,
        var(--iris) 80%,
        transparent) !important;
    opacity: 0.7 !important;
}

div[data-testid="metric-container"]:hover {
    border-color: var(--border-mid) !important;
    transform: translateY(-4px) !important;
    box-shadow: var(--shadow-md), var(--glow-gold) !important;
}

[data-testid="stMetricValue"] {
    font-family: 'Outfit', sans-serif !important;
    font-size: 2rem !important;
    font-weight: 800 !important;
    color: var(--ink-1) !important;
    letter-spacing: -0.04em !important;
    line-height: 1.1 !important;
}

[data-testid="stMetricLabel"] {
    font-size: 0.65rem !important;
    font-weight: 500 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.13em !important;
    color: var(--ink-3) !important;
    margin-bottom: 4px !important;
}

[data-testid="stMetricDelta"] {
    font-size: 0.78rem !important;
    font-weight: 500 !important;
}

/* ─── Divider ────────────────────────────────────────────────── */
hr {
    border: none !important;
    border-top: 1px solid var(--border-faint) !important;
    margin: 0.85rem 0 !important;
}

/* ─── Sidebar Brand ──────────────────────────────────────────── */
.si-brand {
    padding: 24px 20px 16px;
}

.si-wordmark {
    font-family: 'Outfit', sans-serif;
    font-weight: 800;
    font-size: 1.1rem;
    letter-spacing: -0.025em;
    background: linear-gradient(120deg, var(--ink-1) 40%, var(--gold-l));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 2px;
}

.si-eyebrow {
    font-size: 0.65rem;
    font-weight: 500;
    letter-spacing: 0.13em;
    text-transform: uppercase;
    color: var(--ink-3);
}

.si-chip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    margin-top: 10px;
    padding: 3px 10px 3px 8px;
    border-radius: 100px;
    border: 1px solid rgba(0,196,154,0.3);
    background: rgba(0,196,154,0.08);
    font-size: 0.65rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--jade);
}

.si-chip::before {
    content: '';
    width: 6px; height: 6px;
    border-radius: 50%;
    background: var(--jade);
    box-shadow: 0 0 8px var(--jade);
    animation: pulse-dot 2s ease-in-out infinite;
}

@keyframes pulse-dot {
    0%, 100% { opacity: 1; transform: scale(1); }
    50%       { opacity: 0.5; transform: scale(0.8); }
}

/* ─── Sidebar Nav Radio ──────────────────────────────────────── */
.stRadio > label {
    display: none !important;
}

.stRadio > div {
    gap: 2px !important;
    padding: 0 12px !important;
}

/* Style the radio circle to match design system */
.stRadio > div > label > div:first-child {
    border-color: var(--border-faint) !important;
    background: var(--base) !important;
    width: 16px !important;
    height: 16px !important;
    flex-shrink: 0 !important;
}

.stRadio > div > label[data-checked="true"] > div:first-child {
    border-color: var(--iris) !important;
    background: var(--iris) !important;
    box-shadow: 0 0 8px rgba(124,131,245,0.5) !important;
    width: 16px !important;
    height: 16px !important;
    min-width: 16px !important;
    min-height: 16px !important;
}

.stRadio > div > label[data-checked="true"] > div:first-child > div {
    display: none !important;
}

/* Hide the actual radio circle input */

.stRadio > div > label {
    border-radius: var(--r-sm) !important;
    padding: 9px 12px !important;
    width: 100% !important;
    cursor: pointer !important;
    display: flex !important;
    align-items: center !important;
    gap: 8px !important;
    font-family: 'Outfit', sans-serif !important;
    font-size: 0.9rem !important;
    font-weight: 500 !important;
    color: var(--ink-2) !important;
    transition: all 0.15s ease !important;
    border: 1px solid transparent !important;
    letter-spacing: -0.01em !important;
    background: transparent !important;
}

.stRadio > div > label:hover {
    color: var(--gold-l) !important;
    border-color: var(--border-faint) !important;
    background: transparent !important;
}

.stRadio > div > label[data-checked="true"] {
    color: var(--iris-l) !important;
    border-color: rgba(124,131,245,0.25) !important;
    font-weight: 600 !important;
    background: rgba(124,131,245,0.1) !important;
    border-left: 3px solid var(--iris) !important;
    padding-left: 10px !important;
}

/* ─── Buttons ────────────────────────────────────────────────── */
.stButton > button {
    width: 100% !important;
    border-radius: var(--r-sm) !important;
    height: 42px !important;
    font-family: 'Figtree', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.8rem !important;
    letter-spacing: 0.04em !important;
    transition: all 0.18s cubic-bezier(0.4,0,0.2,1) !important;
    cursor: pointer !important;
    position: relative !important;
    overflow: hidden !important;
}

/* Primary button — first in each column */
div[data-testid="column"]:first-child .stButton > button,
.stButton > button[kind="primary"] {
    border: 1px solid var(--border-mid) !important;
    background: var(--overlay) !important;
    color: var(--ink-1) !important;
}

.stButton > button {
    border: 1px solid var(--border-subtle) !important;
    background: transparent !important;
    color: var(--ink-2) !important;
}

.stButton > button:hover {
    background: rgba(124,131,245,0.1) !important;
    border-color: rgba(124,131,245,0.35) !important;
    color: var(--iris-l) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 16px rgba(124,131,245,0.12) !important;
}

.stButton > button:active {
    transform: translateY(0) scale(0.99) !important;
}

/* ─── Inputs ─────────────────────────────────────────────────── */
.stTextInput input,
.stSelectbox > div > div {
    border-radius: var(--r-sm) !important;
    background: var(--surface) !important;
    border: 1px solid var(--border-subtle) !important;
    color: var(--ink-1) !important;
    font-family: 'Figtree', sans-serif !important;
    font-size: 0.875rem !important;
    transition: border-color 0.18s ease, box-shadow 0.18s ease !important;
}

.stTextInput input:focus,
.stSelectbox > div > div:focus-within {
    border-color: rgba(124,131,245,0.5) !important;
    box-shadow: 0 0 0 3px rgba(124,131,245,0.1) !important;
    outline: none !important;
}

.stTextInput label, .stSelectbox label {
    font-size: 0.65rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.1em !important;
    color: var(--ink-3) !important;
}

/* ─── Alert Cards ────────────────────────────────────────────── */
.alert-wrap { display: flex; flex-direction: column; gap: 10px; }

.alert-card {
    border-radius: var(--r-md);
    padding: 16px 18px;
    position: relative;
    overflow: hidden;
    backdrop-filter: blur(8px);
    transition: transform 0.18s ease;
}

.alert-card:hover { transform: translateX(3px); }

.alert-card .a-indicator {
    position: absolute;
    left: 0; top: 0; bottom: 0;
    width: 3px;
    border-radius: 3px 0 0 3px;
}

.alert-card .a-header {
    font-family: 'Outfit', sans-serif;
    font-size: 0.85rem;
    font-weight: 700;
    margin-bottom: 4px;
    display: flex;
    align-items: center;
    gap: 8px;
}

.alert-card .a-body {
    font-size: 0.83rem;
    color: var(--ink-2);
    line-height: 1.5;
    margin-bottom: 8px;
}

.alert-card .a-meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    color: var(--ink-3);
    letter-spacing: 0.02em;
}

.alert-high {
    background: linear-gradient(135deg,
        rgba(240,82,110,0.1) 0%,
        rgba(240,82,110,0.04) 100%);
    border: 1px solid rgba(240,82,110,0.18);
}
.alert-high .a-indicator { background: var(--rose); box-shadow: 0 0 12px var(--rose-d); }
.alert-high .a-header   { color: var(--rose-l); }

.alert-medium {
    background: linear-gradient(135deg,
        rgba(240,165,0,0.1) 0%,
        rgba(240,165,0,0.04) 100%);
    border: 1px solid rgba(240,165,0,0.18);
}
.alert-medium .a-indicator { background: var(--gold); box-shadow: 0 0 12px var(--gold-d); }
.alert-medium .a-header   { color: var(--gold-l); }

.alert-low {
    background: linear-gradient(135deg,
        rgba(124,131,245,0.1) 0%,
        rgba(124,131,245,0.04) 100%);
    border: 1px solid rgba(124,131,245,0.18);
}
.alert-low .a-indicator { background: var(--iris); box-shadow: 0 0 12px var(--iris-d); }
.alert-low .a-header   { color: var(--iris-l); }

/* ─── Page header ────────────────────────────────────────────── */
.page-header {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    margin-bottom: 1.75rem;
    padding-bottom: 1.25rem;
    border-bottom: 1px solid var(--border-faint);
}

.page-header-meta {
    font-size: 0.78rem;
    color: var(--ink-3);
    text-align: right;
    line-height: 1.6;
}

.page-header-meta strong {
    color: var(--iris-l);
    font-weight: 500;
}

/* ─── Section labels ─────────────────────────────────────────── */
.section-label {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 1.75rem 0 1rem;
}

.section-label-line {
    flex: 1;
    height: 1px;
    background: var(--border-faint);
}

.section-label-text {
    font-size: 0.65rem;
    font-weight: 600;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--ink-3);
    white-space: nowrap;
}

/* ─── DataFrames ─────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border-radius: var(--r-md) !important;
    overflow: hidden !important;
    border: 1px solid var(--border-subtle) !important;
    box-shadow: var(--shadow-sm) !important;
}

/* ─── Plotly chart wrapper ───────────────────────────────────── */
[data-testid="stPlotlyChart"] {
    background: var(--raised) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--r-md) !important;
    padding: 2px !important;
    box-shadow: var(--shadow-sm) !important;
    transition: box-shadow 0.22s ease !important;
}

[data-testid="stPlotlyChart"]:hover {
    box-shadow: var(--shadow-md) !important;
}

/* ─── Status callouts ────────────────────────────────────────── */
.stSuccess {
    background: rgba(0,196,154,0.08) !important;
    border: 1px solid rgba(0,196,154,0.2) !important;
    border-radius: var(--r-sm) !important;
}

.stInfo {
    background: rgba(124,131,245,0.08) !important;
    border: 1px solid rgba(124,131,245,0.2) !important;
    border-radius: var(--r-sm) !important;
}

.stWarning {
    background: rgba(240,165,0,0.08) !important;
    border: 1px solid rgba(240,165,0,0.2) !important;
    border-radius: var(--r-sm) !important;
}

.stError {
    background: rgba(240,82,110,0.08) !important;
    border: 1px solid rgba(240,82,110,0.2) !important;
    border-radius: var(--r-sm) !important;
}

/* ─── Code blocks ────────────────────────────────────────────── */
code, pre, .stCode {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.78rem !important;
    background: var(--surface) !important;
    border: 1px solid var(--border-faint) !important;
    border-radius: var(--r-sm) !important;
    color: var(--jade-l) !important;
}

/* ─── Caption ────────────────────────────────────────────────── */
.stCaption, [data-testid="stCaptionContainer"] {
    font-size: 0.7rem !important;
    color: var(--ink-3) !important;
}

/* ─── Scrollbar ──────────────────────────────────────────────── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
    background: var(--border-mid);
    border-radius: 999px;
}
::-webkit-scrollbar-thumb:hover { background: var(--border-bright); }

/* ─── Sidebar inner padding ──────────────────────────────────── */
section[data-testid="stSidebar"] .stRadio,
section[data-testid="stSidebar"] .stSelectbox,
section[data-testid="stSidebar"] .stTextInput,
section[data-testid="stSidebar"] .stButton {
    padding-left: 0 !important;
    padding-right: 0 !important;
}

section[data-testid="stSidebar"] .stSelectbox,
section[data-testid="stSidebar"] .stTextInput {
    padding: 0 12px !important;
}

section[data-testid="stSidebar"] .stButton {
    padding: 0 12px !important;
}

/* Sidebar section headings */
.si-section-head {
    font-family: 'Outfit', sans-serif;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    padding: 14px 20px 6px;
    background: linear-gradient(120deg, var(--ink-2) 30%, var(--gold-l));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

</style>
""", unsafe_allow_html=True)

# ── Plotly theme ───────────────────────────────────────────────────────────────
_FONT = "Figtree, system-ui, sans-serif"
_FONT_TITLE = "Outfit, sans-serif"

PLOTLY_LAYOUT = dict(
    plot_bgcolor  = "rgba(0,0,0,0)",
    paper_bgcolor = "rgba(0,0,0,0)",
    font          = dict(family=_FONT, size=12, color="#64748b"),
    title_font    = dict(family=_FONT_TITLE, size=14, color="#f1f5f9"),
    xaxis=dict(
        gridcolor        = "rgba(255,255,255,0.04)",
        zerolinecolor    = "rgba(255,255,255,0.07)",
        tickfont         = dict(size=11, color="#475569"),
        linecolor        = "rgba(255,255,255,0.06)",
        title_font       = dict(size=11, color="#475569"),
    ),
    yaxis=dict(
        gridcolor        = "rgba(255,255,255,0.04)",
        zerolinecolor    = "rgba(255,255,255,0.07)",
        tickfont         = dict(size=11, color="#475569"),
        linecolor        = "rgba(0,0,0,0)",
        title_font       = dict(size=11, color="#475569"),
    ),
    legend=dict(
        bgcolor      = "rgba(22,32,47,0.8)",
        bordercolor  = "rgba(148,163,184,0.12)",
        borderwidth  = 1,
        font         = dict(size=11, color="#94a3b8"),
    ),
    margin  = dict(l=20, r=20, t=44, b=20),
    hoverlabel = dict(
        bgcolor    = "#1c2a3d",
        bordercolor= "rgba(148,163,184,0.2)",
        font       = dict(family=_FONT, size=12, color="#f1f5f9"),
    ),
)

# Colour palettes
PALETTE_GOLD_IRIS = [
    [0.0, "#1e1040"], [0.25, "#4338ca"],
    [0.55, "#f0a500"], [1.0,  "#ffd166"],
]
PALETTE_JADE = [
    [0.0, "#041a14"], [0.4, "#009070"], [1.0, "#4ee8c2"],
]
PALETTE_SKY = [
    [0.0, "#03111f"], [0.5, "#0e6fa8"], [1.0, "#90d8f7"],
]
PALETTE_HEAT = [
    [0.0, "#1a0510"], [0.35, "#b02050"],
    [0.7, "#16a34a"], [1.0, "#86efac"],
]

# Discrete colours
C_IRIS  = "#7c83f5"
C_GOLD  = "#f0a500"
C_JADE  = "#00c49a"
C_ROSE  = "#f0526e"
C_SKY   = "#38b9f0"
C_VIOLET= "#a78bfa"

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
        <div class="si-brand">
            <div class="si-wordmark">🏪 Store Intelligence</div>
            <div class="si-eyebrow">AI-Powered Retail Analytics</div>
            <div><span class="si-chip">Live Dashboard</span></div>
        </div>
    """, unsafe_allow_html=True)
    st.divider()

    # Store selector
    try:
        con    = duckdb.connect(DB_PATH, read_only=True)
        stores = [r[0] for r in con.execute(
            "SELECT DISTINCT store_id FROM events ORDER BY 1"
        ).fetchall()]
        con.close()
    except Exception:
        stores = []

    st.markdown('<div class="si-section-head">Store</div>', unsafe_allow_html=True)
    store_options  = ["ALL"] + stores
    selected_store = st.selectbox("Store", store_options, label_visibility="collapsed")
    store_id       = None if selected_store == "ALL" else selected_store

    st.divider()

    st.markdown('<div class="si-section-head">Process</div>', unsafe_allow_html=True)
    process_store_id = st.text_input(
        "Store ID",
        placeholder="e.g. STORE_001",
        label_visibility="collapsed",
    )
    if st.button("⚡ Run CV Pipeline"):

        # ---------------------------
        # ROOT PATH SETUP (safe)
        # ---------------------------
        BASE_DIR = Path(__file__).resolve().parent
        PROJECT_ROOT = BASE_DIR.parent.parent

        STORE_DIR = PROJECT_ROOT / "Data" / process_store_id
        output_file = PROJECT_ROOT / "events.jsonl"
        DB_PATH = STORE_DIR / "store_intelligence.db"


        layout_dir = STORE_DIR / "Layout"
        layouts = list(layout_dir.glob("*.json"))
        layout_file = layouts[0]


        # ---------------------------
        # LOAD VIDEOS (safe)
        # ---------------------------
        video_dir = STORE_DIR / "MP4"

        if not video_dir.exists():
            st.error(f"❌ MP4 folder missing: {video_dir}")
            st.stop()

        videos = list(video_dir.glob("*.mp4"))

        if not videos:
            st.error("❌ No MP4 files found")
            st.stop()

        st.success(f"🎥 Found {len(videos)} videos")

        # ---------------------------
        # RUN PIPELINE
        # ---------------------------
        success_count = 0

        for idx, video in enumerate(videos):

            cmd = [
                sys.executable,
                str(BASE_DIR.parent / "pipeline/cv_pipeline.py"),
                "--video", str(video),
                "--layout", str(layout_file),
                "--store", process_store_id,
                "--camera", f"CAM{idx+1}",
                "--output", str(output_file),
            ]

            st.code(" ".join(cmd))

            result = subprocess.run(cmd, capture_output=True, text=True)


            if result.stderr:
                st.error(result.stderr)

            if result.returncode == 0:
                success_count += 1

        # ---------------------------
        # FINAL STATUS
        # ---------------------------
        if success_count == len(videos):
            st.success(f"✅ Successfully processed {len(videos)} videos for {process_store_id}")
        else:
            st.warning(f"⚠️ Processed {success_count}/{len(videos)} videos")

    st.divider()

    st.markdown('<div class="si-section-head">Navigation</div>', unsafe_allow_html=True)
    page = st.radio("Navigation", [
        "Overview",
        "Zone Heatmap",
        "Demographics",
        "Revenue & Brands",
        "Alerts",
        "Zone → Purchase",
    ], label_visibility="collapsed")

    st.divider()

    if st.button("↺  Refresh Data"):
        BASE_DIR     = Path(__file__).resolve().parent
        PROJECT_ROOT = BASE_DIR.parent
        try:
            subprocess.run(
                [sys.executable, str(PROJECT_ROOT / "pipeline/normalizer.py")],
                capture_output=True, text=True, check=True,
            )
            st.success("Normalised ✓")
            st.cache_data.clear()
            st.rerun()
        except subprocess.CalledProcessError as e:
            st.error(e.stderr)

    st.markdown(f"""
        <div style="padding:12px 20px 20px; margin-top:auto;">
            <div style="font-family:'JetBrains Mono',monospace; font-size:0.65rem;
                        color:var(--ink-4); line-height:1.8;">
                DB · <span style="color:var(--ink-3)">{DB_PATH}</span><br>
                At · <span style="color:var(--ink-3)">{datetime.now().strftime('%H:%M:%S')}</span>
            </div>
        </div>
    """, unsafe_allow_html=True)


# ── Data loaders (cached 60 s) ─────────────────────────────────────────────────
@st.cache_data(ttl=60)
def get_footfall(sid): return footfall_summary(sid, DB_PATH)
@st.cache_data(ttl=60)
def get_hourly(sid):   return hourly_footfall(sid, DB_PATH)
@st.cache_data(ttl=60)
def get_demo(sid):     return demographic_breakdown(sid, DB_PATH)
@st.cache_data(ttl=60)
def get_zones(sid):    return zone_heatmap(sid, DB_PATH)
@st.cache_data(ttl=60)
def get_zone_conv(sid):return zone_conversion(sid, DB_PATH)
@st.cache_data(ttl=60)
def get_queue(sid):    return queue_stats(sid, DB_PATH)
@st.cache_data(ttl=60)
def get_revenue(sid):  return revenue_summary(sid, DB_PATH)
@st.cache_data(ttl=60)
def get_brands(sid):   return top_brands(sid, db_path=DB_PATH)
@st.cache_data(ttl=60)
def get_rev_hour(sid): return revenue_by_hour(sid, DB_PATH)
@st.cache_data(ttl=60)
def get_alerts(sid):   return detect_anomalies(sid, DB_PATH)


# ── Helper: section label ──────────────────────────────────────────────────────
def section_label(text: str):
    st.markdown(f"""
        <div class="section-label">
            <div class="section-label-line"></div>
            <div class="section-label-text">{text}</div>
            <div class="section-label-line"></div>
        </div>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE  Overview
# ══════════════════════════════════════════════════════════════════════════════
if page == "Overview":
    # Header
    st.markdown(f"""
        <div class="page-header">
            <div>
                <h1 style="margin:0">Store Overview</h1>
            </div>
            <div class="page-header-meta">
                Viewing <strong>{selected_store}</strong><br>
                {datetime.now().strftime('%d %b %Y · %H:%M')}
            </div>
        </div>
    """, unsafe_allow_html=True)

    ff = get_footfall(store_id)
    q  = get_queue(store_id)
    rv = get_revenue(store_id)

    # KPI row
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total Visitors",  f"{ff.get('total_visitors') or 0:,}")
    c2.metric("Unique Visitors", f"{ff.get('unique_visitors') or 0:,}")
    c3.metric("Conversion",      f"{ff.get('conversion_rate_pct') or 0}%")
    c4.metric("Queue Abandons",  f"{ff.get('queue_abandons') or 0}")
    c5.metric("Revenue",         f"₹{rv.get('total_revenue') or 0:,.0f}")
    c6.metric("Avg Wait P50",    f"{q.get('p50_wait_s') or 0}s")

    section_label("Hourly Footfall")

    hourly = get_hourly(store_id)
    if hourly:
        df_h = pd.DataFrame(hourly)
        fig  = go.Figure()
        fig.add_bar(
            x=df_h["hour"], y=df_h["entries"], name="Entries",
            marker=dict(
                color=C_IRIS, opacity=0.9,
                line=dict(width=0),
            ),
        )
        fig.add_bar(
            x=df_h["hour"], y=df_h["exits"], name="Exits",
            marker=dict(
                color=C_GOLD, opacity=0.85,
                line=dict(width=0),
            ),
        )
        fig.update_layout(
            **PLOTLY_LAYOUT,
            title     = "Hourly Footfall",
            xaxis_title = "Hour of Day",
            yaxis_title = "Visitor Count",
            barmode   = "group",
            height    = 340,
            bargap    = 0.2,
            bargroupgap = 0.07,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hourly data available.")

    section_label("Queue Performance")
    cq1, cq2, cq3, cq4 = st.columns(4)
    cq1.metric("Served",       q.get("total_served") or 0)
    cq2.metric("Abandoned",    q.get("total_abandoned") or 0)
    cq3.metric("Abandon Rate", f"{q.get('abandon_rate_pct') or 0}%")
    cq4.metric("P90 Wait",     f"{q.get('p90_wait_s') or 0}s")


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE  Zone Heatmap
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Zone Heatmap":
    st.markdown("""
        <div class="page-header">
            <div><h1 style="margin:0">Zone Traffic</h1></div>
        </div>
    """, unsafe_allow_html=True)

    zones = get_zones(store_id)
    if not zones:
        st.info("No zone data found.")
    else:
        df_z = pd.DataFrame(zones)
        df_z["zone_visits"] = df_z["zone_visits"].fillna(0)

        fig = px.scatter(
            df_z,
            x="avg_x", y="avg_y",
            size="zone_visits",
            color="zone_visits",
            color_continuous_scale=PALETTE_GOLD_IRIS,
            hover_name="zone_name",
            hover_data={"zone_type": True, "zone_visits": True, "unique_visitors": True},
            size_max=68,
            title="Zone Traffic · bubble size = visit count",
            labels={"avg_x": "X position", "avg_y": "Y position", "zone_visits": "Visits"},
        )
        fig.update_yaxes(autorange="reversed")
        fig.update_layout(
            **PLOTLY_LAYOUT,
            height=480,
            coloraxis_colorbar=dict(
                thickness=12,
                len=0.6,
                tickfont=dict(size=10),
                title_font=dict(size=11),
            ),
        )
        st.plotly_chart(fig, use_container_width=True)

        section_label("Zone Details")
        df_display = df_z[["zone_name","zone_type","zone_visits","unique_visitors","is_revenue_zone"]].copy()
        df_display.columns = ["Zone","Type","Visits","Unique Visitors","Revenue Zone"]
        df_display = df_display.sort_values("Visits", ascending=False)
        st.dataframe(df_display, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE  Demographics
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Demographics":
    st.markdown("""
        <div class="page-header">
            <div><h1 style="margin:0">Visitor Demographics</h1></div>
        </div>
    """, unsafe_allow_html=True)

    demo = get_demo(store_id)
    col1, col2 = st.columns(2)

    with col1:
        gd = demo.get("by_gender", [])
        if gd:
            df_g = pd.DataFrame(gd)
            fig  = px.pie(
                df_g, names="gender", values="count",
                title="Gender Split",
                color_discrete_map={"F": C_ROSE, "M": C_IRIS, "Unknown": "#2d3a4e"},
                hole=0.52,
            )
            fig.update_traces(
                textposition="inside",
                textinfo="percent+label",
                marker=dict(line=dict(color="#0d1221", width=2.5)),
                pull=[0.03] * len(df_g),
            )
            fig.update_layout(**PLOTLY_LAYOUT, height=340, showlegend=True)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No gender data.")

    with col2:
        ad = demo.get("by_age_bucket", [])
        if ad:
            df_a = pd.DataFrame(ad).sort_values("age_bucket")
            fig  = px.bar(
                df_a, x="age_bucket", y="count",
                title="Age Distribution",
                color="count",
                color_continuous_scale=PALETTE_SKY,
                labels={"age_bucket": "Age Group", "count": "Visitors"},
            )
            fig.update_traces(
                marker_line_width=0,
                marker_cornerradius=4,
            )
            fig.update_layout(**PLOTLY_LAYOUT, height=340, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No age data.")

    section_label("Group Composition")
    ff = get_footfall(store_id)
    cg1, cg2 = st.columns(2)
    cg1.metric("Group Visitors", ff.get("group_visitors") or 0)
    cg2.metric("Solo Visitors",
               (ff.get("total_visitors") or 0) - (ff.get("group_visitors") or 0))


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE  Revenue & Brands
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Revenue & Brands":
    st.markdown("""
        <div class="page-header">
            <div><h1 style="margin:0">Revenue & Brands</h1></div>
        </div>
    """, unsafe_allow_html=True)

    rv = get_revenue(store_id)
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Total Revenue",  f"₹{rv.get('total_revenue') or 0:,.2f}")
    r2.metric("Total Orders",   rv.get("total_orders") or 0)
    r3.metric("Avg Item Value", f"₹{rv.get('avg_item_value') or 0:,.2f}")
    r4.metric("Unique Brands",  rv.get("unique_brands") or 0)

    section_label("Revenue Over Time")

    col_l, col_r = st.columns([3, 2])

    with col_l:
        rev_hour = get_rev_hour(store_id)
        if rev_hour:
            df_rh = pd.DataFrame(rev_hour)
            fig   = go.Figure()
            fig.add_bar(
                x=df_rh["hour"], y=df_rh["revenue"],
                name="Revenue (₹)",
                marker=dict(color=C_JADE, opacity=0.9, line=dict(width=0)),
            )
            fig.add_scatter(
                x=df_rh["hour"], y=df_rh["orders"],
                name="Orders", yaxis="y2",
                mode="lines+markers",
                line=dict(color=C_GOLD, width=2.5),
                marker=dict(size=7, color=C_GOLD,
                            line=dict(width=2, color="#0d1221")),
            )
            layout = dict(PLOTLY_LAYOUT)
            layout["yaxis"]  = {**layout.get("yaxis",{}),
                                 "title": "Revenue (₹)",
                                 "gridcolor": "rgba(255,255,255,0.04)"}
            layout["yaxis2"] = {"title": "Orders", "overlaying": "y",
                                 "side": "right",
                                 "gridcolor": "rgba(0,0,0,0)",
                                 "tickfont": {"color": C_GOLD}}
            layout["title"]  = "Revenue & Orders by Hour"
            layout["height"] = 340
            fig.update_layout(layout)
            st.plotly_chart(fig, use_container_width=True)

    with col_r:
        brands = get_brands(store_id)
        if brands:
            df_b = pd.DataFrame(brands)
            fig  = px.bar(
                df_b.head(10),
                x="revenue", y="brand",
                orientation="h",
                title="Top Brands by Revenue",
                color="revenue",
                color_continuous_scale=PALETTE_SKY,
                labels={"brand": "", "revenue": "₹"},
            )
            fig.update_traces(marker_line_width=0, marker_cornerradius=3)
            layout = dict(PLOTLY_LAYOUT)
            layout["yaxis"]       = {**layout.get("yaxis",{}), "autorange": "reversed"}
            layout["showlegend"]  = False
            layout["height"]      = 370
            fig.update_layout(layout)
            st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE  Alerts
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Alerts":
    st.markdown("""
        <div class="page-header">
            <div><h1 style="margin:0">Anomaly Alerts</h1></div>
        </div>
    """, unsafe_allow_html=True)

    alerts = get_alerts(store_id)
    if not alerts:
        st.success("✅  No anomalies detected — all systems nominal.")
    else:
        high   = [a for a in alerts if a["severity"] == "high"]
        medium = [a for a in alerts if a["severity"] == "medium"]
        low    = [a for a in alerts if a["severity"] == "low"]

        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("🔴  High",   len(high))
        sc2.metric("🟡  Medium", len(medium))
        sc3.metric("🔵  Low",    len(low))

        section_label("Active Alerts")

        def render_alert(a, css_class, icon, label):
            st.markdown(f"""
                <div class="alert-card {css_class}">
                    <div class="a-indicator"></div>
                    <div style="padding-left:12px">
                        <div class="a-header">{icon} {label} · {a["type"].replace("_"," ").title()}</div>
                        <div class="a-body">{a["detail"]}</div>
                        <div class="a-meta">
                            Visitor: {a["visitor_id"]} &nbsp;·&nbsp;
                            Store: {a["store_id"]} &nbsp;·&nbsp;
                            {a.get("timestamp","")}
                        </div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

        st.markdown('<div class="alert-wrap">', unsafe_allow_html=True)
        for a in high:   render_alert(a, "alert-high",   "●", "HIGH")
        for a in medium: render_alert(a, "alert-medium", "●", "MEDIUM")
        for a in low:    render_alert(a, "alert-low",    "●", "LOW")
        st.markdown('</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE  Zone → Purchase
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Zone → Purchase":
    st.markdown("""
        <div class="page-header">
            <div><h1 style="margin:0">Zone → Purchase</h1></div>
        </div>
    """, unsafe_allow_html=True)
    st.caption("Which zones drove purchases? Conversion = zone visitors who completed a queue transaction.")

    conv = get_zone_conv(store_id)
    if not conv:
        st.info("No attribution data available.")
    else:
        df_c = pd.DataFrame(conv)

        fig = px.bar(
            df_c,
            x="conversion_pct", y="zone_name",
            orientation="h",
            color="conversion_pct",
            color_continuous_scale=PALETTE_HEAT,
            text="conversion_pct",
            hover_data={"total_visitors": True, "buyers": True},
            title="Conversion Rate by Zone",
            labels={"zone_name": "", "conversion_pct": "Conversion %"},
        )
        fig.update_traces(
            texttemplate="%{text}%",
            textposition="outside",
            marker_line_width=0,
            marker_cornerradius=4,
        )
        layout = dict(PLOTLY_LAYOUT)
        layout["yaxis"]       = {**layout.get("yaxis",{}), "autorange": "reversed"}
        layout["height"]      = 440
        layout["showlegend"]  = False
        layout["coloraxis_colorbar"] = dict(
            thickness=10, len=0.5,
            tickfont=dict(size=10),
        )
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True)

        section_label("Attribution Table")
        df_c["conversion_pct"] = df_c["conversion_pct"].apply(lambda x: f"{x}%")
        st.dataframe(
            df_c[["zone_name","total_visitors","buyers","conversion_pct"]].rename(columns={
                "zone_name":       "Zone",
                "total_visitors":  "Zone Visitors",
                "buyers":          "Buyers",
                "conversion_pct":  "Conversion Rate",
            }),
            use_container_width=True,
            hide_index=True,
        )
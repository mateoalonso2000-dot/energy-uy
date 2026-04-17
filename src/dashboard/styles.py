"""
styles.py — CSS custom para el dashboard AIC Energy UY.

Aplica la identidad visual de AIC Economía & Finanzas:
  Navy #1D3461 | Verde #27AE60 | Blanco | Fondo #F8FAFC
  Tipografía: Inter (Google Fonts)
"""

AIC_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

/* ── Tipografía base ─────────────────────────────────────────── */
html, body, [class*="css"], .stMarkdown, .stText {
    font-family: 'Inter', sans-serif !important;
}

/* ── Sidebar navy ────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background-color: #1D3461 !important;
}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stMarkdown {
    color: #FFFFFF !important;
}
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stCheckbox label {
    color: rgba(255,255,255,0.85) !important;
    font-size: 13px;
    font-weight: 500;
}
[data-testid="stSidebar"] [data-baseweb="select"] > div {
    background-color: #253F73 !important;
    border-color: #3A5A96 !important;
    color: #FFFFFF !important;
}
[data-testid="stSidebar"] [data-baseweb="select"] span {
    color: #FFFFFF !important;
}
[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.18) !important;
    margin: 16px 0;
}
[data-testid="stSidebar"] .stCheckbox span {
    color: rgba(255,255,255,0.85) !important;
}

/* ── Botón primario verde ─────────────────────────────────────── */
.stButton > button[kind="primary"] {
    background-color: #27AE60 !important;
    border-color: #27AE60 !important;
    color: #FFFFFF !important;
    font-weight: 600;
    font-family: 'Inter', sans-serif;
    width: 100%;
    padding: 0.6rem 1rem;
    border-radius: 6px;
    letter-spacing: 0.01em;
    transition: background-color 0.15s ease;
}
.stButton > button[kind="primary"]:hover {
    background-color: #219A52 !important;
    border-color: #219A52 !important;
}
.stButton > button[kind="primary"]:disabled {
    opacity: 0.5 !important;
}

/* ── KPI cards ───────────────────────────────────────────────── */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 28px;
}
.kpi-card {
    background: #FFFFFF;
    border-radius: 8px;
    padding: 20px 22px;
    border-left: 4px solid #27AE60;
    box-shadow: 0 1px 4px rgba(29,52,97,0.07), 0 0 0 1px rgba(29,52,97,0.04);
}
.kpi-card.accent-thermal { border-left-color: #E07B39; }
.kpi-card.accent-hydro   { border-left-color: #2980B9; }
.kpi-card.accent-wind    { border-left-color: #5DADE2; }
.kpi-card .kpi-label {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #8896B0;
    margin-bottom: 10px;
}
.kpi-card .kpi-value {
    font-size: 26px;
    font-weight: 700;
    color: #1D3461;
    font-variant-numeric: tabular-nums;
    line-height: 1.1;
}
.kpi-card .kpi-delta {
    font-size: 12px;
    color: #27AE60;
    margin-top: 6px;
    font-weight: 500;
}
.kpi-card .kpi-delta.neutral {
    color: #8896B0;
}

/* ── Header principal ────────────────────────────────────────── */
.main-header {
    background: linear-gradient(135deg, #1D3461 0%, #2C4A7C 100%);
    border-radius: 10px;
    padding: 18px 24px;
    margin-bottom: 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.header-left {
    display: flex;
    align-items: center;
    gap: 18px;
}
.header-logo {
    height: 48px;
    width: auto;
    background: #FFFFFF;
    border-radius: 7px;
    padding: 5px 12px;
    flex-shrink: 0;
    display: block;
}
.main-header h1 {
    font-size: 20px !important;
    font-weight: 700 !important;
    color: #FFFFFF !important;
    margin: 0 !important;
    padding: 0 !important;
    line-height: 1.2;
}
.main-header .header-sub {
    font-size: 12px;
    color: rgba(255,255,255,0.6);
    margin-top: 4px;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}
.main-header .period-badge {
    background: rgba(39,174,96,0.18);
    border: 1px solid rgba(39,174,96,0.45);
    color: #4ADE80;
    font-size: 13px;
    font-weight: 600;
    padding: 7px 18px;
    border-radius: 20px;
    white-space: nowrap;
    font-family: 'Inter', sans-serif;
}

/* ── Logo en sidebar ─────────────────────────────────────────── */
.aic-logo {
    padding: 4px 0 22px 0;
    border-bottom: 1px solid rgba(255,255,255,0.15);
    margin-bottom: 22px;
}
.sidebar-logo-img {
    width: 100%;
    max-width: 175px;
    height: auto;
    border-radius: 7px;
    display: block;
    margin-bottom: 10px;
}
.aic-logo .logo-product {
    font-size: 12px;
    color: rgba(255,255,255,0.75);
    margin-top: 2px;
    font-weight: 500;
    font-family: 'Inter', sans-serif;
    letter-spacing: 0.03em;
}

/* ── Status indicator ────────────────────────────────────────── */
.run-status {
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: 12px;
    color: rgba(255,255,255,0.65);
    margin-top: 10px;
    font-family: 'Inter', sans-serif;
}
.status-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #27AE60;
    flex-shrink: 0;
}

/* ── Section labels ──────────────────────────────────────────── */
.section-label {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.09em;
    color: #8896B0;
    margin: 20px 0 12px 0;
    padding-bottom: 8px;
    border-bottom: 1px solid #E8EDF5;
    font-family: 'Inter', sans-serif;
}

/* ── Empty state ─────────────────────────────────────────────── */
.empty-state {
    text-align: center;
    padding: 72px 20px;
}
.empty-state .empty-icon {
    font-size: 40px;
    margin-bottom: 16px;
    opacity: 0.35;
}
.empty-state h3 {
    font-size: 17px;
    font-weight: 600;
    color: #64748B;
    margin-bottom: 8px;
    font-family: 'Inter', sans-serif;
}
.empty-state p {
    font-size: 14px;
    color: #94A3B8;
    max-width: 360px;
    margin: 0 auto;
    line-height: 1.6;
    font-family: 'Inter', sans-serif;
}

/* ── LinkedIn copy textarea ──────────────────────────────────── */
.stTextArea textarea {
    font-family: 'Inter', sans-serif !important;
    font-size: 14px !important;
    line-height: 1.7 !important;
    color: #1D3461 !important;
    border-color: #D1D9E6 !important;
    border-radius: 8px !important;
}
.stTextArea textarea:focus {
    border-color: #27AE60 !important;
    box-shadow: 0 0 0 3px rgba(39,174,96,0.12) !important;
}

/* ── Tabs ────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    border-bottom: 2px solid #E8EDF5;
}
.stTabs [data-baseweb="tab"] {
    font-size: 13px;
    font-weight: 600;
    color: #8896B0;
    padding: 8px 20px;
    border-radius: 6px 6px 0 0;
    font-family: 'Inter', sans-serif;
}
.stTabs [aria-selected="true"] {
    color: #1D3461 !important;
    border-bottom: 2px solid #27AE60 !important;
}

/* ── Botón colapsar/expandir sidebar ─────────────────────────── */
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"],
button[aria-label="Open sidebar"],
button[aria-label="Abrir barra lateral"],
section[data-testid="stSidebarContent"] ~ div > button {
    background-color: #CBD5E1 !important;
    border-radius: 0 6px 6px 0 !important;
    box-shadow: 2px 0 6px rgba(0,0,0,0.12) !important;
    opacity: 1 !important;
    visibility: visible !important;
}
[data-testid="collapsedControl"]:hover,
[data-testid="stSidebarCollapsedControl"]:hover,
button[aria-label="Open sidebar"]:hover {
    background-color: #94A3B8 !important;
}
[data-testid="collapsedControl"] svg,
[data-testid="stSidebarCollapsedControl"] svg {
    color: #1D3461 !important;
    fill: #1D3461 !important;
}

/* ── Ocultar branding Streamlit ──────────────────────────────── */
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
header    { visibility: hidden; }
</style>
"""

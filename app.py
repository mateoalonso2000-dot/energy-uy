"""
app.py — Dashboard Streamlit para el Sistema Eléctrico Uruguayo.
AIC Economía & Finanzas

Uso:
    streamlit run app.py
"""

import calendar
import sys
from datetime import date
from pathlib import Path

import streamlit as st

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dashboard.styles import AIC_CSS
from src.dashboard.pipeline_runner import (
    PipelineResult,
    MONTHS_ES,
    run_pipeline,
)
from src.dashboard.components.kpi_cards import render_kpi_row
from src.dashboard.components.charts_tab import render_charts_tab
from src.dashboard.components.linkedin_panel import render_linkedin_tab
from src.dashboard.health_check import run_health_check


# ── Configuración de página ───────────────────────────────────────────────────
st.set_page_config(
    page_title="AIC | Sistema Eléctrico Uruguay",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(AIC_CSS, unsafe_allow_html=True)

# ── Health check (conectividad) ───────────────────────────────────────────────
run_health_check()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:

    # Logo AIC
    st.markdown("""
    <div class="aic-logo">
        <div class="logo-wordmark">&#9644; <span class="green">AIC</span></div>
        <div class="logo-tagline">Economía &amp; Finanzas</div>
        <div class="logo-product">Sistema Eléctrico Uruguay</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(
        "<p style='font-size:12px; font-weight:700; text-transform:uppercase; "
        "letter-spacing:0.08em; color:rgba(255,255,255,0.5); margin-bottom:10px;'>"
        "Período de análisis</p>",
        unsafe_allow_html=True,
    )

    today = date.today()
    # Por defecto: mes anterior
    default_month = today.month - 1 if today.month > 1 else 12
    default_year  = today.year if today.month > 1 else today.year - 1

    col_m, col_y = st.columns(2)
    with col_m:
        month = st.selectbox(
            "Mes",
            options=list(range(1, 13)),
            index=default_month - 1,
            format_func=lambda m: MONTHS_ES[m].capitalize(),
        )
    with col_y:
        year_options = list(range(2023, today.year + 1))
        year = st.selectbox(
            "Año",
            options=year_options,
            index=year_options.index(default_year),
        )

    last_day  = calendar.monthrange(year, month)[1]
    date_from = date(year, month, 1)
    date_to   = date(year, month, last_day)

    st.markdown("---")

    skip_fetch  = st.checkbox(
        "Usar datos ya descargados",
        value=False,
        help="Omite la descarga y usa los datos que ya están en la base de datos local.",
    )

    run_clicked = st.button("▶  Ejecutar pipeline", type="primary")

    # Estado de última ejecución
    if "last_run_label" in st.session_state:
        st.markdown(
            f'<div class="run-status">'
            f'<div class="status-dot"></div>'
            f'Últ. ejecución: {st.session_state.last_run_label}'
            f'</div>',
            unsafe_allow_html=True,
        )


# ── Trigger del pipeline ──────────────────────────────────────────────────────
if run_clicked:
    progress_bar = st.progress(0.0, text="Iniciando pipeline...")

    def update_progress(msg: str, pct: float) -> None:
        progress_bar.progress(min(pct, 1.0), text=msg)

    with st.spinner(""):
        result: PipelineResult = run_pipeline(
            date_from=date_from,
            date_to=date_to,
            skip_fetch=skip_fetch,
            progress_callback=update_progress,
        )

    progress_bar.empty()
    st.session_state.result          = result
    st.session_state.last_run_label  = f"{MONTHS_ES[month].capitalize()} {year}"

    if result.errors:
        for err in result.errors:
            st.warning(f"Advertencia: {err}")

    if result.df_gen.empty:
        st.error(
            "No se encontraron datos de generación para el período seleccionado. "
            "Verificá que el rango de fechas tenga datos disponibles."
        )


# ── Contenido principal ───────────────────────────────────────────────────────
result: PipelineResult | None = st.session_state.get("result")

# Header con período activo
period_str = (
    f"{MONTHS_ES[date_from.month].capitalize()} {date_from.year}"
    if date_from.month == date_to.month
    else f"{date_from.strftime('%d/%m/%Y')} — {date_to.strftime('%d/%m/%Y')}"
)

st.markdown(f"""
<div class="main-header">
    <div>
        <h1>Sistema Eléctrico Uruguayo</h1>
        <div class="header-sub">AIC Economía &amp; Finanzas &nbsp;·&nbsp; Fuente: ADME / UTE</div>
    </div>
    <div class="period-badge">{period_str}</div>
</div>
""", unsafe_allow_html=True)

# Estado vacío inicial
if result is None:
    st.markdown("""
    <div class="empty-state">
        <div class="empty-icon">⚡</div>
        <h3>Sin datos cargados</h3>
        <p>Seleccioná un período en el panel izquierdo y hacé clic en
        <strong>Ejecutar pipeline</strong> para ver el análisis.</p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

if result.df_gen.empty:
    st.stop()

# KPI cards (siempre visibles encima de los tabs)
render_kpi_row(result)

# Tabs
tab_gen, tab_linkedin = st.tabs(["Generación", "LinkedIn"])

with tab_gen:
    render_charts_tab(result)

with tab_linkedin:
    render_linkedin_tab(result)

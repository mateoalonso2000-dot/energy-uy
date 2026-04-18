"""
kpi_cards.py — Fila de 4 tarjetas KPI para el dashboard.
"""

import streamlit as st

from src.dashboard.pipeline_runner import PipelineResult, SOURCE_NAMES_ES


def render_kpi_row(result: PipelineResult) -> None:
    """Renderiza la fila de 4 KPIs con estilos AIC."""

    top_name  = SOURCE_NAMES_ES.get(result.top_source, result.top_source.capitalize())
    price_str = f"{result.avg_price_usd:.1f}" if result.avg_price_usd else "—"
    price_unit = "USD/MWh" if result.avg_price_usd else ""

    # Variación precio vs mes anterior
    price_delta_html = f'<div class="kpi-delta neutral">{price_unit if price_unit else "sin datos de precio"}</div>'
    if result.avg_price_usd and result.prev_avg_price_usd:
        delta_pct = (result.avg_price_usd - result.prev_avg_price_usd) / result.prev_avg_price_usd * 100
        arrow     = "▲" if delta_pct > 0 else "▼"
        d_color   = "#E74C3C" if delta_pct > 0 else "#27AE60"
        price_delta_html = (
            f'<div class="kpi-delta" style="color:{d_color};">'
            f'{arrow} {abs(delta_pct):.1f}% vs. mes anterior</div>'
        )

    # Color del border-left según renovabilidad
    ren_pct = result.renewable_pct
    if ren_pct >= 90:
        ren_color = "#27AE60"
    elif ren_pct >= 70:
        ren_color = "#F39C12"
    else:
        ren_color = "#E74C3C"

    st.markdown(f"""
    <div class="kpi-grid">
        <div class="kpi-card" style="border-left-color: {ren_color};">
            <div class="kpi-label">Generación Renovable</div>
            <div class="kpi-value">{ren_pct:.1f}%</div>
            <div class="kpi-delta" style="color:{ren_color};">del total generado</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Fuente Líder</div>
            <div class="kpi-value" style="font-size:22px;">{top_name}</div>
            <div class="kpi-delta">{result.top_source_pct:.1f}% de participación</div>
        </div>
        <div class="kpi-card" style="border-left-color: #2980B9;">
            <div class="kpi-label">Precio Spot Promedio</div>
            <div class="kpi-value">{price_str}</div>
            {price_delta_html}
        </div>
        <div class="kpi-card" style="border-left-color: #8896B0;">
            <div class="kpi-label">Período analizado</div>
            <div class="kpi-value" style="font-size:17px;">{result.period_label.capitalize()}</div>
            <div class="kpi-delta neutral">{result.date_from.strftime("%d/%m")} — {result.date_to.strftime("%d/%m/%Y")}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

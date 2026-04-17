"""
charts_tab.py — Tab de visualizaciones del dashboard.
Usa Plotly para gráficos interactivos.
"""

import streamlit as st

from src.dashboard.pipeline_runner import PipelineResult


def render_charts_tab(result: PipelineResult) -> None:
    """
    Muestra los 4 gráficos del pipeline en un grid 2x2.
    Los go.Figure de Plotly se renderizan con st.plotly_chart().
    """
    charts = result.charts

    if not charts:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-icon">📊</div>
            <h3>Sin gráficos disponibles</h3>
            <p>Ejecutá el pipeline para generar las visualizaciones.</p>
        </div>
        """, unsafe_allow_html=True)
        return

    # Fila 1: Donut (composición) + Área (serie temporal)
    col1, col2 = st.columns(2, gap="medium")

    with col1:
        if "donut" in charts:
            st.plotly_chart(charts["donut"], use_container_width=True)

    with col2:
        if "area" in charts:
            st.plotly_chart(charts["area"], use_container_width=True)

    st.markdown("<div style='margin-top: 8px;'></div>", unsafe_allow_html=True)

    # Fila 2: Barras (renovable vs no renovable) + YoY
    col3, col4 = st.columns(2, gap="medium")

    with col3:
        if "bar" in charts:
            st.plotly_chart(charts["bar"], use_container_width=True)

    with col4:
        if "yoy" in charts:
            st.plotly_chart(charts["yoy"], use_container_width=True)

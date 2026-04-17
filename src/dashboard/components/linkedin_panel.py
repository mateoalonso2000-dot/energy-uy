"""
linkedin_panel.py — Tab de contenido editorial para LinkedIn.
"""

import streamlit as st

from src.dashboard.pipeline_runner import PipelineResult


def render_linkedin_tab(result: PipelineResult) -> None:
    """
    Muestra el copy de LinkedIn editable y los bullets de respaldo.
    """
    st.markdown('<div class="section-label">Borrador para LinkedIn</div>', unsafe_allow_html=True)

    if not result.linkedin_copy:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-icon">✍️</div>
            <h3>Sin copy generado</h3>
            <p>Ejecutá el pipeline para generar el borrador editorial.</p>
        </div>
        """, unsafe_allow_html=True)
        return

    col_edit, col_info = st.columns([3, 1], gap="large")

    with col_edit:
        edited = st.text_area(
            label="copy",
            value=result.linkedin_copy,
            height=420,
            label_visibility="collapsed",
            help="Editá el copy antes de publicarlo. Los cambios no se guardan automáticamente.",
        )

        # Instrucción para copiar (la clipboard API no está disponible en Streamlit nativo)
        st.caption("Seleccioná todo el texto (Ctrl+A dentro del campo) y copiá con Ctrl+C.")

    with col_info:
        st.markdown('<div class="section-label">Datos de respaldo</div>', unsafe_allow_html=True)

        if result.bullets:
            for bullet in result.bullets:
                st.markdown(
                    f"<p style='font-size:13px; color:#4A5568; line-height:1.6; "
                    f"margin-bottom:10px;'>• {bullet}</p>",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("Sin bullets disponibles.")

        st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)
        st.markdown(
            f"<p style='font-size:11px; color:#94A3B8;'>Fuente: ADME / UTE<br>"
            f"Período: {result.period_label}</p>",
            unsafe_allow_html=True,
        )

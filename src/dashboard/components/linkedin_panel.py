"""
linkedin_panel.py — Tab de contenido editorial para LinkedIn.
"""

import json

import streamlit as st
import streamlit.components.v1 as components

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
        line_count     = result.linkedin_copy.count("\n") + 1
        dynamic_height = max(280, min(520, line_count * 22))

        edited = st.text_area(
            label="copy",
            value=result.linkedin_copy,
            height=dynamic_height,
            label_visibility="collapsed",
            help="Editá el copy antes de publicarlo. Los cambios no se guardan automáticamente.",
        )

        # Botón copiar al portapapeles via JS
        text_json = json.dumps(edited)
        components.html(f"""
        <style>
        #copy-btn {{
            background: #27AE60;
            color: #fff;
            border: none;
            border-radius: 6px;
            padding: 8px 18px;
            font-size: 14px;
            font-family: Inter, sans-serif;
            font-weight: 600;
            cursor: pointer;
            width: 100%;
            transition: background 0.15s;
        }}
        #copy-btn:hover {{ background: #219A52; }}
        #copy-btn.copied {{ background: #1D3461; }}
        </style>
        <button id="copy-btn" onclick="copyPost()">📋 Copiar post</button>
        <script>
        function copyPost() {{
            var text = {text_json};
            var el = document.createElement('textarea');
            el.value = text;
            el.style.position = 'fixed';
            el.style.opacity = '0';
            document.body.appendChild(el);
            el.focus();
            el.select();
            document.execCommand('copy');
            document.body.removeChild(el);
            var btn = document.getElementById('copy-btn');
            btn.textContent = '✓ ¡Post copiado!';
            btn.classList.add('copied');
            setTimeout(function() {{
                btn.textContent = '📋 Copiar post';
                btn.classList.remove('copied');
            }}, 2000);
        }}
        </script>
        """, height=52)

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

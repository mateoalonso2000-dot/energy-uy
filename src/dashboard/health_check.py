"""
health_check.py — Validaciones de arranque para el dashboard.

Se ejecuta una vez al cargar la app. Verifica conectividad con ADME
y muestra advertencias en el dashboard si algo no está disponible.
No bloquea la carga de la app: los errores son informativos.
"""

import streamlit as st

import config


@st.cache_data(ttl=300, show_spinner=False)
def _check_adme() -> tuple[bool, str]:
    """
    Verifica que el endpoint principal de ADME sea alcanzable.
    Cacheado 5 minutos para no hacer un HTTP por cada re-render.

    Returns:
        (True, "") si es alcanzable.
        (False, mensaje_de_error) si falla.
    """
    import httpx

    try:
        with httpx.Client(timeout=8, headers=config.HTTP_HEADERS) as client:
            resp = client.get(config.ADME_BASE_URL, follow_redirects=True)
            resp.raise_for_status()
        return True, ""
    except Exception as exc:
        return False, str(exc)


def run_health_check() -> None:
    """
    Ejecuta los chequeos de arranque y muestra advertencias en el dashboard.

    Llamar una sola vez, al inicio de app.py, antes de renderizar contenido.
    No lanza excepciones: todos los problemas se muestran como st.warning/error.
    """
    adme_ok, adme_err = _check_adme()

    if not adme_ok:
        st.warning(
            f"**ADME no alcanzable** — No se pudo conectar con "
            f"`{config.ADME_BASE_URL}`. "
            "El pipeline fallará al intentar descargar datos. "
            "Verificá tu conexión o reintentá en unos minutos. "
            f"Detalle: `{adme_err}`",
            icon="⚠️",
        )

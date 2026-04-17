"""
config.py — Configuración central del proyecto energy-uy.

Orden de resolución de cada variable:
  1. st.secrets  — Streamlit Cloud (UI "Settings → Secrets") o local
                   .streamlit/secrets.toml
  2. os.getenv   — archivo .env cargado por python-dotenv (desarrollo local)
  3. valor por defecto en código

Importar este módulo en lugar de usar os.environ directamente.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Cargar .env desde la raíz del proyecto (no-op si el archivo no existe)
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")


def _get_config(key: str, default: str = "") -> str:
    """
    Lee una variable de configuración con fallback en cascada:
    st.secrets → os.getenv → default.

    Cuando se ejecuta fuera del contexto de Streamlit (scripts CLI, tests),
    st.secrets no está disponible; el bloque try/except silencia el error
    y cae directamente al os.getenv.
    """
    try:
        import streamlit as st
        val = st.secrets.get(key)
        if val is not None:
            return str(val)
    except Exception:
        pass
    return os.getenv(key, default)

# ─── Rutas ────────────────────────────────────────────────────────────────────

_db_path_raw = _get_config("DB_PATH", "data/db/energy_uy.sqlite")
# Si el valor es absoluto (ej: /tmp/energy_uy.sqlite en cloud), usarlo directo.
# Si es relativo, anclarlo a la raíz del proyecto.
DB_PATH = Path(_db_path_raw) if Path(_db_path_raw).is_absolute() else ROOT_DIR / _db_path_raw

OUTPUT_DIR = ROOT_DIR / _get_config("OUTPUT_DIR", "outputs")
CHARTS_DIR = OUTPUT_DIR / "charts"
REPORTS_DIR = OUTPUT_DIR / "reports"

# Crear directorios si no existen
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
CHARTS_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ─── HTTP ─────────────────────────────────────────────────────────────────────

HTTP_TIMEOUT = int(_get_config("HTTP_TIMEOUT", "30"))
HTTP_USER_AGENT = _get_config(
    "HTTP_USER_AGENT",
    "Mozilla/5.0 (compatible; energy-uy-pipeline/0.1)",
)
HTTP_HEADERS = {"User-Agent": HTTP_USER_AGENT}

# ─── Fuentes de datos ─────────────────────────────────────────────────────────

ADME_BASE_URL = _get_config("ADME_BASE_URL", "https://adme.com.uy")
UTE_BASE_URL  = _get_config("UTE_BASE_URL",  "https://apps.ute.com.uy")

# Endpoints específicos (ajustar si ADME/UTE modifican su estructura)
ADME_DATOS_ABIERTOS_URL = f"{ADME_BASE_URL}/datosabiertos.html"
ADME_CONTROL_PANEL_URL  = f"{ADME_BASE_URL}/controlpanel.php"
UTE_BAJADAS_URL         = f"{UTE_BASE_URL}/SgePublico/Bajadas.aspx"

# SCADA GPF — subdominio confirmado con pruebas reales
# El formulario recibe fecha_ini/fecha_fin y devuelve HTML con link al ODS
ADME_GPF_BASE_URL = _get_config("ADME_GPF_BASE_URL", "https://pronos.adme.com.uy")
ADME_GPF_URL      = f"{ADME_GPF_BASE_URL}/gpf.php"

# Panel de Control ADME — generación mensual por fuente (xlsx)
# Confirmado: GET adme.com.uy/panelControl/gpf_excel.php (sin www)
ADME_GENERACION_MENSUAL_URL = "https://adme.com.uy/panelControl/gpf_excel.php"

# Panel de Control ADME — precio spot sancionado en USD/MWh (xlsx, resolución horaria)
# Confirmado: GET www.adme.com.uy/panelControl/sancionado_excel.php (con www)
ADME_PRECIO_SPOT_URL = "https://www.adme.com.uy/panelControl/sancionado_excel.php"

# ─── Estado de fuentes ────────────────────────────────────────────────────────
# Cambiar a "true" en secrets / .env cuando la fuente vuelva a estar operativa.
UTE_BAJADAS_ENABLED = _get_config("UTE_BAJADAS_ENABLED", "false").lower() == "true"

# ─── Logging ──────────────────────────────────────────────────────────────────

LOG_LEVEL = _get_config("LOG_LEVEL", "INFO")

# ─── Dominio del sistema eléctrico ───────────────────────────────────────────

# Mapeo canónico de fuentes a tipo (renovable / no renovable)
SOURCE_TYPE_MAP: dict[str, str] = {
    "wind":     "renewable",
    "solar":    "renewable",
    "hydro":    "renewable",
    "biomass":  "renewable",
    "thermal":  "non_renewable",
    "import":   "external",
    "export":   "external",
}

# Nombres en español → nombres canónicos internos
SOURCE_NAME_MAP: dict[str, str] = {
    "eólica":   "wind",
    "eolica":   "wind",
    "viento":   "wind",
    "solar":    "solar",
    "fotovoltaica": "solar",
    "hidro":    "hydro",
    "hidráulica": "hydro",
    "hidraulica": "hydro",
    "térmica":  "thermal",
    "termica":  "thermal",
    "biomasa":  "biomass",
    "biomass":  "biomass",
}

# Zona horaria del sistema eléctrico uruguayo
TIMEZONE = "America/Montevideo"

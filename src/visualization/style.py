"""
style.py — Paleta de colores, tipografía y tema global para todos los gráficos.

Modificar aquí para cambiar la identidad visual de todas las visualizaciones
sin tocar el código de los gráficos individuales.
"""

import matplotlib.pyplot as plt
import matplotlib as mpl

# ─── Paleta de colores por fuente de energía ─────────────────────────────────

COLORS = {
    "wind":          "#4A90D9",   # azul
    "solar":         "#F5A623",   # amarillo-naranja
    "hydro":         "#7ED321",   # verde claro
    "biomass":       "#8B572A",   # marrón
    "thermal":       "#9B9B9B",   # gris
    "import":        "#BD10E0",   # violeta
    "export":        "#D0021B",   # rojo
    "renewable":     "#417505",   # verde oscuro
    "non_renewable": "#D0021B",   # rojo
    "demand":        "#2C3E50",   # azul muy oscuro
}

# Nombres en español para leyendas
SOURCE_LABELS = {
    "wind":          "Eólica",
    "solar":         "Solar",
    "hydro":         "Hidráulica",
    "biomass":       "Biomasa",
    "thermal":       "Térmica",
    "import":        "Importación",
    "export":        "Exportación",
    "renewable":     "Renovable",
    "non_renewable": "No renovable",
    "demand":        "Demanda",
}

# Orden preferido para gráficos de área/barra (de mayor a menor renovabilidad)
SOURCE_ORDER = ["hydro", "wind", "solar", "biomass", "thermal", "import", "export"]

# ─── Dimensiones de exportación ──────────────────────────────────────────────

FIGSIZE_LINKEDIN  = (10, 6)   # ratio 5:3 — óptimo para feed de LinkedIn
FIGSIZE_SQUARE    = (8, 8)    # para gráficos de composición (donut)
DPI_HIGH          = 300       # alta resolución (impresión, presentaciones)
DPI_WEB           = 150       # optimizado para redes sociales

# ─── Tipografía y texto ───────────────────────────────────────────────────────

FONT_FAMILY   = "DejaVu Sans"
FONT_TITLE    = 14
FONT_SUBTITLE = 10
FONT_AXIS     = 9
FONT_TICK     = 8
FONT_LEGEND   = 8
FONT_FOOTER   = 7

# ─── Colores del tema ─────────────────────────────────────────────────────────

COLOR_BG        = "#FFFFFF"
COLOR_GRID      = "#E8E8E8"
COLOR_TEXT      = "#2C3E50"
COLOR_SUBTITLE  = "#7F8C8D"
COLOR_FOOTER    = "#95A5A6"

# ─── Aplicar tema global ──────────────────────────────────────────────────────

def apply_theme() -> None:
    """
    Aplica el tema visual de energy-uy a matplotlib de forma global.
    Llamar una vez al inicio del proceso de visualización.
    """
    mpl.rcParams.update({
        "figure.facecolor":     COLOR_BG,
        "axes.facecolor":       COLOR_BG,
        "axes.edgecolor":       COLOR_GRID,
        "axes.labelcolor":      COLOR_TEXT,
        "axes.labelsize":       FONT_AXIS,
        "axes.titlesize":       FONT_TITLE,
        "axes.grid":            True,
        "axes.axisbelow":       True,
        "grid.color":           COLOR_GRID,
        "grid.linewidth":       0.8,
        "xtick.labelsize":      FONT_TICK,
        "ytick.labelsize":      FONT_TICK,
        "xtick.color":          COLOR_TEXT,
        "ytick.color":          COLOR_TEXT,
        "legend.fontsize":      FONT_LEGEND,
        "legend.frameon":       False,
        "font.family":          FONT_FAMILY,
        "text.color":           COLOR_TEXT,
        "savefig.facecolor":    COLOR_BG,
        "savefig.bbox":         "tight",
        "savefig.pad_inches":   0.15,
    })


def add_footer(ax: plt.Axes, source_text: str, date_text: str) -> None:
    """
    Agrega nota al pie con fuente y fecha al gráfico.

    Args:
        ax:          Axes de matplotlib
        source_text: texto de fuente (ej: "Fuente: ADME / UTE")
        date_text:   texto de fecha (ej: "Período: enero 2024")
    """
    ax.figure.text(
        0.01, 0.01,
        f"{source_text}  |  {date_text}",
        ha="left",
        va="bottom",
        fontsize=FONT_FOOTER,
        color=COLOR_FOOTER,
        style="italic",
    )


def add_title_block(fig: plt.Figure, title: str, subtitle: str = "") -> None:
    """
    Agrega título y subtítulo en la parte superior de la figura.
    Útil para gráficos con múltiples ejes (subplots).
    """
    fig.suptitle(title, fontsize=FONT_TITLE, fontweight="bold", color=COLOR_TEXT, y=1.01)
    if subtitle:
        fig.text(
            0.5, 0.98,
            subtitle,
            ha="center",
            va="top",
            fontsize=FONT_SUBTITLE,
            color=COLOR_SUBTITLE,
        )

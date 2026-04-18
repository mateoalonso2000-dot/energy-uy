"""
editorial_export.py — Exportación editorial de alta calidad para LinkedIn.

Genera imágenes PNG de 1200x675px con composición profesional:
header navy AIC + logo + título periodístico, gráfico de área apilada,
footer con atribución de datos.
"""

import io
import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")   # backend no interactivo, seguro en servidores
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from PIL import Image

logger = logging.getLogger(__name__)

# ── Rutas ─────────────────────────────────────────────────────────────────────
_ROOT      = Path(__file__).parent.parent.parent
_LOGO_PATH = _ROOT / "assets" / "logo_aic.png"

# ── Dimensiones (LinkedIn landscape) ─────────────────────────────────────────
IMG_W = 1200
IMG_H = 675
DPI   = 100
FIG_W = IMG_W / DPI   # 12.0 inches
FIG_H = IMG_H / DPI   # 6.75 inches

# Proporciones de secciones en coordenadas de figura (0=bottom, 1=top)
_HDR_H  = 0.15        # header: 15%
_FTR_H  = 0.10        # footer: 10%
_LGD_H  = 0.065       # leyenda: 6.5%
_BODY_H = 1.0 - _HDR_H - _FTR_H - _LGD_H   # ~68.5%

_HDR_BOTTOM  = 1.0 - _HDR_H                  # 0.85
_FTR_BOTTOM  = 0.0
_LGD_BOTTOM  = _FTR_H                         # 0.10
_BODY_BOTTOM = _FTR_H + _LGD_H               # 0.165

# ── Paleta AIC ────────────────────────────────────────────────────────────────
_NAVY      = "#1D3461"
_GREEN     = "#27AE60"
_FOOTER_BG = "#F7F7F7"
_GRID      = "#F0F0F0"
_WHITE     = "#FFFFFF"
_SUBTEXT   = "#94A3B8"
_DARK_TEXT = "#4A5568"
_BORDER    = "#E2E8F0"

_NAVY_RGB = (29, 52, 97)

_COLORS = {
    "hydro":    "#27AE60",
    "wind":     "#1D3461",
    "solar":    "#F0A500",
    "biomass":  "#1E8449",
    "thermal":  "#8896B0",
    "import":   "#3A5A96",
    "export":   "#C0392B",
}

_SOURCE_LABELS = {
    "wind":    "Eólica",
    "solar":   "Solar",
    "hydro":   "Hidráulica",
    "biomass": "Biomasa",
    "thermal": "Térmica",
    "import":  "Importación",
    "export":  "Exportación",
}

_SOURCE_ORDER = ["hydro", "wind", "solar", "biomass", "thermal", "import", "export"]


# ── API pública ───────────────────────────────────────────────────────────────

def export_mix_generacion(
    df: pd.DataFrame,
    periodo_label: str,
    output_path: Path | None = None,
) -> bytes:
    """
    Genera imagen PNG 1200x675px del mix de generación eléctrica.

    Args:
        df:            DataFrame con columnas: date, source, value_mwh
        periodo_label: string del período, ej: "marzo 2026"
        output_path:   si se provee, guarda en disco; siempre retorna bytes

    Returns:
        bytes del PNG generado (listo para st.image() o st.download_button())
    """
    titulo    = _build_title(df, periodo_label)
    subtitulo = f"Participación por fuente en GWh.  Período: {periodo_label}."

    fig = _build_figure(df, titulo=titulo, subtitulo=subtitulo, periodo_label=periodo_label)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, bbox_inches=None, facecolor=_WHITE)
    plt.close(fig)
    buf.seek(0)
    png_bytes = buf.read()

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(png_bytes)
        logger.info("Imagen editorial guardada: %s", output_path)

    return png_bytes


# ── Lógica de título ──────────────────────────────────────────────────────────

def _build_title(df: pd.DataFrame, periodo_label: str) -> str:
    """Genera título periodístico dinámico según los datos del período."""
    try:
        from src.analysis.indicators import renewable_share, generation_mix, leading_source

        ren = renewable_share(df)
        pct = ren["renewable_pct"]

        if pct > 85:
            return f"Uruguay generó con {pct:.0f}% de energía renovable en {periodo_label}"

        mix = generation_mix(df)
        if not mix.empty:
            top = leading_source(mix)
            name = _SOURCE_LABELS.get(top["source"], top["source"]).lower()
            if top["share_pct"] >= 40:
                return f"La {name} lideró la generación eléctrica en {periodo_label}"
    except Exception as exc:
        logger.warning("No se pudo calcular título dinámico: %s", exc)

    return f"Mix de generación eléctrica de Uruguay — {periodo_label}"


# ── Construcción de la figura ─────────────────────────────────────────────────

def _build_figure(
    df: pd.DataFrame,
    titulo: str,
    subtitulo: str,
    periodo_label: str,
) -> plt.Figure:
    """Construye la figura completa: header, gráfico, leyenda y footer."""
    # Limpiar estado de matplotlib para evitar interferencias entre llamadas
    plt.rcParams.update(plt.rcParamsDefault)

    fig = plt.figure(figsize=(FIG_W, FIG_H), dpi=DPI)
    fig.patch.set_facecolor(_WHITE)

    # ── Header ──────────────────────────────────────────────────────────────────
    ax_hdr = fig.add_axes([0.0, _HDR_BOTTOM, 1.0, _HDR_H])
    _draw_header(fig, ax_hdr, titulo, subtitulo)

    # ── Cuerpo (gráfico de área) ─────────────────────────────────────────────
    # Padding interno: izq 7%, der 2%, 1% de padding top/bottom
    ax_body = fig.add_axes([0.07, _BODY_BOTTOM + 0.012, 0.91, _BODY_H - 0.024])
    _draw_chart(ax_body, df)

    # ── Leyenda horizontal ────────────────────────────────────────────────────
    ax_lgd = fig.add_axes([0.05, _LGD_BOTTOM + 0.005, 0.90, _LGD_H - 0.010])
    ax_lgd.set_facecolor(_WHITE)
    ax_lgd.axis("off")
    _draw_legend(ax_lgd, ax_body)

    # ── Footer ───────────────────────────────────────────────────────────────
    ax_ftr = fig.add_axes([0.0, _FTR_BOTTOM, 1.0, _FTR_H])
    _draw_footer(ax_ftr, periodo_label)

    return fig


# ── Secciones de la figura ───────────────────────────────────────────────────

def _draw_header(
    fig: plt.Figure,
    ax: plt.Axes,
    titulo: str,
    subtitulo: str,
) -> None:
    """Dibuja el header: fondo navy, logo AIC, título y subtítulo."""
    ax.set_facecolor(_NAVY)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # ── Logo ──────────────────────────────────────────────────────────────────
    title_x_ax = 0.025  # posición x del título en ax.transAxes (fallback sin logo)

    try:
        img_pil = Image.open(_LOGO_PATH).convert("RGBA")

        # Compositar logo sobre fondo navy para eliminar transparencia
        bg = Image.new("RGBA", img_pil.size, (*_NAVY_RGB, 255))
        composited = Image.alpha_composite(bg, img_pil).convert("RGB")
        logo_arr = np.array(composited)

        # Altura del logo: 72% de la sección header en fracciones de figura
        logo_h_fig = _HDR_H * 0.72
        # Ancho proporcional al aspect ratio del logo original
        aspect = img_pil.width / img_pil.height
        logo_w_fig = logo_h_fig * aspect * (FIG_H / FIG_W)

        # Posición: margen izquierdo, centrado verticalmente en el header
        logo_left_fig = 0.025
        logo_bot_fig  = _HDR_BOTTOM + (_HDR_H - logo_h_fig) / 2

        ax_logo = fig.add_axes([logo_left_fig, logo_bot_fig, logo_w_fig, logo_h_fig])
        ax_logo.imshow(logo_arr, aspect="auto")
        ax_logo.axis("off")

        # Inicio del texto = derecha del logo + gap pequeño
        title_x_fig = logo_left_fig + logo_w_fig + 0.025
        # Como ax_hdr cubre el ancho completo (0→1), transAxes x == figure x
        title_x_ax = title_x_fig

    except Exception as exc:
        logger.warning("Logo no disponible: %s", exc)

    # ── Título ────────────────────────────────────────────────────────────────
    # Truncar si es muy largo para evitar overflow
    t = titulo if len(titulo) <= 78 else titulo[:75] + "…"

    ax.text(
        title_x_ax, 0.63, t,
        ha="left", va="center",
        color=_WHITE,
        fontsize=12.5,
        fontweight="bold",
        transform=ax.transAxes,
        clip_on=True,
    )

    # ── Subtítulo ─────────────────────────────────────────────────────────────
    if subtitulo:
        ax.text(
            title_x_ax, 0.22, subtitulo,
            ha="left", va="center",
            color=_SUBTEXT,
            fontsize=8.5,
            transform=ax.transAxes,
            clip_on=True,
        )


def _draw_chart(ax: plt.Axes, df: pd.DataFrame) -> None:
    """Dibuja el gráfico de área apilada del mix de generación."""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])

    df_pivot = df.pivot_table(
        index="date",
        columns="source",
        values="value_mwh",
        aggfunc="sum",
        fill_value=0,
    )
    ordered = [c for c in _SOURCE_ORDER if c in df_pivot.columns]
    extra   = [c for c in df_pivot.columns if c not in ordered]
    df_pivot = df_pivot[ordered + extra]

    ax.set_facecolor(_WHITE)

    ys     = [df_pivot[s].values / 1000 for s in df_pivot.columns]  # MWh → GWh
    colors = [_COLORS.get(s, "#CCCCCC") for s in df_pivot.columns]
    labels = [_SOURCE_LABELS.get(s, s.capitalize()) for s in df_pivot.columns]

    ax.stackplot(df_pivot.index, *ys, labels=labels, colors=colors, alpha=0.88)

    # ── Formato de ejes ───────────────────────────────────────────────────────
    ax.set_ylabel("GWh", fontsize=9, color=_DARK_TEXT, labelpad=4)
    ax.tick_params(axis="both", labelsize=8.5, colors=_DARK_TEXT, length=3)

    n_days = len(df_pivot)
    if n_days <= 14:
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
    elif n_days <= 31:
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0))
    else:
        ax.xaxis.set_major_locator(mdates.MonthLocator())

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.tick_params(axis="x", rotation=0)

    # ── Grilla suave, sin spines ──────────────────────────────────────────────
    ax.yaxis.grid(True, color=_GRID, linewidth=0.8, zorder=0)
    ax.xaxis.grid(True, color=_GRID, linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)

    for spine in ax.spines.values():
        spine.set_visible(False)


def _draw_legend(ax_lgd: plt.Axes, ax_body: plt.Axes) -> None:
    """Dibuja la leyenda horizontal centrada debajo del gráfico."""
    handles, labels = ax_body.get_legend_handles_labels()
    if not handles:
        return

    ax_lgd.legend(
        handles, labels,
        loc="center",
        ncol=min(len(labels), 6),
        fontsize=8.5,
        frameon=False,
        handlelength=1.4,
        handleheight=0.8,
        columnspacing=1.4,
        handletextpad=0.5,
    )


def _draw_footer(ax: plt.Axes, periodo_label: str) -> None:
    """Dibuja el footer: fondo claro, texto de fuente y marca AIC."""
    ax.set_facecolor(_FOOTER_BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # Línea divisoria superior
    ax.plot([0.02, 0.98], [0.97, 0.97], color=_BORDER, linewidth=0.8, transform=ax.transAxes)

    # Texto izquierdo: fuente de datos
    ax.text(
        0.025, 0.42,
        f"Fuente: ADME (Administración del Mercado Eléctrico)  |  Período: {periodo_label}",
        ha="left", va="center",
        color=_DARK_TEXT,
        fontsize=7.5,
        transform=ax.transAxes,
    )

    # Texto derecho: marca AIC
    ax.text(
        0.975, 0.42,
        "AIC Economía & Finanzas — aic.com.uy",
        ha="right", va="center",
        color=_DARK_TEXT,
        fontsize=7.5,
        transform=ax.transAxes,
    )

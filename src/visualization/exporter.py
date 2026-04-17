"""
exporter.py — Exportación de figuras matplotlib a archivos PNG.

Genera dos versiones de cada gráfico:
- Alta resolución (300 dpi) para presentaciones e impresión.
- Versión web (150 dpi) optimizada para LinkedIn y redes sociales.
"""

import logging
from pathlib import Path

import matplotlib.pyplot as plt

from src.visualization.style import DPI_HIGH, DPI_WEB

logger = logging.getLogger(__name__)


def export_chart(
    fig: plt.Figure,
    output_dir: Path,
    filename_stem: str,
    formats: list[str] | None = None,
) -> dict[str, Path]:
    """
    Exporta una figura en alta resolución y versión web.

    Args:
        fig:           figura de matplotlib
        output_dir:    directorio de destino
        filename_stem: nombre base sin extensión ni sufijo
                       (ej: 'mix_generacion_area_202401')
        formats:       lista de formatos a generar, por defecto ['high', 'web']
                       'high' → 300 dpi | 'web' → 150 dpi

    Returns:
        dict con las rutas generadas: {'high': Path, 'web': Path}
    """
    if formats is None:
        formats = ["high", "web"]

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {}

    for fmt in formats:
        dpi = DPI_HIGH if fmt == "high" else DPI_WEB
        suffix = "hires" if fmt == "high" else "web"
        filename = output_dir / f"{filename_stem}_{suffix}.png"

        fig.savefig(filename, dpi=dpi, bbox_inches="tight", facecolor="white")
        logger.info("Gráfico exportado: %s", filename)
        paths[fmt] = filename

    plt.close(fig)
    return paths


def export_all_charts(
    charts: dict[str, plt.Figure],
    output_dir: Path,
    date_slug: str,
) -> dict[str, dict[str, Path]]:
    """
    Exporta un diccionario de gráficos en lote.

    Args:
        charts:     dict {nombre_chart: figura}
        output_dir: directorio base de salida
        date_slug:  sufijo de fecha para los archivos (ej: '2024-01')

    Returns:
        dict anidado {nombre_chart: {'high': Path, 'web': Path}}
    """
    day_dir = output_dir / date_slug
    results = {}

    for name, fig in charts.items():
        stem = f"{name}_{date_slug}"
        results[name] = export_chart(fig, day_dir, stem)

    return results

"""
pipeline_runner.py — Orquestador del pipeline para la Streamlit app.

Encapsula la lógica de adquisición → limpieza → almacenamiento → análisis →
visualización → editorial y retorna un PipelineResult con todo lo necesario
para renderizar el dashboard.
"""

import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from src.connectors.adme_scada import AdmeScadaConnector
from src.connectors.adme_precio_spot import AdmePrecioSpotConnector
from src.processing.cleaner import clean_generation_hourly, clean_spot_price
from src.processing.transformer import aggregate_hourly_to_daily, monthly_summary
from src.storage.database import get_engine, init_db
from src.storage.models import generation_daily, generation_hourly, spot_price
from src.storage.repository import (
    log_ingestion,
    query_generation_daily,
    query_spot_price,
    upsert_dataframe,
)
from src.analysis.indicators import generation_mix, renewable_share, leading_source
from src.visualization.charts import (
    chart_generation_area,
    chart_generation_donut,
    chart_renewables_vs_nonrenewables,
    chart_yoy_comparison,
)
from src.editorial.findings import build_findings
from src.editorial.renderer import build_linkedin_copy

logger = logging.getLogger(__name__)

MONTHS_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo",  6: "junio",  7: "julio",  8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}

SOURCE_NAMES_ES = {
    "wind":    "Eólica",
    "solar":   "Solar",
    "hydro":   "Hidráulica",
    "biomass": "Biomasa",
    "thermal": "Térmica",
    "import":  "Importación",
}


def period_label(date_from: date, date_to: date) -> str:
    if date_from.year == date_to.year and date_from.month == date_to.month:
        return f"{MONTHS_ES[date_from.month]} {date_from.year}"
    return f"{date_from.strftime('%d/%m/%Y')} al {date_to.strftime('%d/%m/%Y')}"


@dataclass
class PipelineResult:
    """Contenedor de resultados para el dashboard."""
    period_label: str
    date_from: date
    date_to: date
    # DataFrames
    df_gen: pd.DataFrame       = field(default_factory=pd.DataFrame)
    df_price: pd.DataFrame     = field(default_factory=pd.DataFrame)
    # Indicadores calculados
    mix: pd.DataFrame          = field(default_factory=pd.DataFrame)
    renewable_pct: float       = 0.0
    top_source: str            = ""
    top_source_pct: float      = 0.0
    avg_price_usd: Optional[float] = None
    # Gráficos (Figure objects de matplotlib)
    charts: dict               = field(default_factory=dict)
    # Editorial
    linkedin_copy: str         = ""
    bullets: list              = field(default_factory=list)
    # Estado de ejecución
    errors: list               = field(default_factory=list)
    skipped_fetch: bool        = False


def run_pipeline(
    date_from: date,
    date_to: date,
    skip_fetch: bool = False,
    progress_callback: Optional[Callable[[str, float], None]] = None,
) -> PipelineResult:
    """
    Ejecuta el pipeline completo y retorna PipelineResult para el dashboard.

    Args:
        date_from:         fecha inicio (inclusive)
        date_to:           fecha fin (inclusive)
        skip_fetch:        omitir descarga y usar datos ya almacenados en DB
        progress_callback: función(mensaje, porcentaje 0–1) para actualizar la UI
    """
    def progress(msg: str, pct: float) -> None:
        logger.info(msg)
        if progress_callback:
            progress_callback(msg, pct)

    label  = period_label(date_from, date_to)
    result = PipelineResult(period_label=label, date_from=date_from, date_to=date_to)

    engine = get_engine(config.DB_PATH)
    init_db(engine)

    # ── A. Adquisición ────────────────────────────────────────────────────────
    if not skip_fetch:
        _fetch_scada(engine, date_from, date_to, result, progress)
        _fetch_precio_spot(engine, date_from, date_to, result, progress)
    else:
        result.skipped_fetch = True
        progress("Usando datos ya almacenados en la base de datos.", 0.4)

    # ── B. Consulta ───────────────────────────────────────────────────────────
    progress("Consultando base de datos...", 0.5)
    result.df_gen   = query_generation_daily(engine, date_from.isoformat(), date_to.isoformat())
    result.df_price = query_spot_price(engine, date_from.isoformat(), date_to.isoformat(), granularity="daily")

    if result.df_gen.empty:
        result.errors.append("No hay datos de generación para el período seleccionado.")
        return result

    # ── C. Indicadores ────────────────────────────────────────────────────────
    progress("Calculando indicadores...", 0.6)
    result.mix          = generation_mix(result.df_gen)
    ren                 = renewable_share(result.df_gen)
    result.renewable_pct = ren["renewable_pct"]

    top                  = leading_source(result.mix)
    result.top_source    = top["source"]
    result.top_source_pct = top["share_pct"]

    if not result.df_price.empty:
        price_col            = "price_usd" if "price_usd" in result.df_price.columns else "price_uyu"
        result.avg_price_usd = round(result.df_price[price_col].mean(), 2)

    # ── D. Gráficos ───────────────────────────────────────────────────────────
    progress("Generando gráficos...", 0.72)
    _build_charts(engine, date_from, date_to, label, result)

    # ── E. Editorial ──────────────────────────────────────────────────────────
    progress("Generando copy para LinkedIn...", 0.90)
    findings            = build_findings(
        df_gen=result.df_gen,
        period_label=label,
        df_price=result.df_price if not result.df_price.empty else None,
    )
    result.bullets      = findings.bullets
    result.linkedin_copy = build_linkedin_copy(findings)

    progress("Pipeline completado.", 1.0)
    return result


# ── Helpers privados ──────────────────────────────────────────────────────────

def _fetch_scada(engine, date_from, date_to, result, progress):
    progress("Descargando generación ADME SCADA...", 0.10)
    t0 = time.time()
    try:
        conn     = AdmeScadaConnector()
        df_raw   = conn.fetch(date_from, date_to)
        df_clean = clean_generation_hourly(df_raw)
        upsert_dataframe(engine, generation_hourly, df_clean)
        df_daily = aggregate_hourly_to_daily(df_clean)
        df_daily["data_source"] = "adme_scada"
        upsert_dataframe(engine, generation_daily, df_daily)
        log_ingestion(engine, "adme_scada", "generation_hourly",
                      date_from.isoformat(), date_to.isoformat(),
                      len(df_raw), len(df_daily), "success",
                      duration_sec=time.time() - t0)
        progress("ADME SCADA: OK.", 0.30)
    except Exception as exc:
        result.errors.append(f"ADME SCADA: {exc}")
        logger.error("ADME SCADA falló: %s", exc)
        log_ingestion(engine, "adme_scada", "generation_hourly",
                      date_from.isoformat(), date_to.isoformat(),
                      0, 0, "error", str(exc), time.time() - t0)


def _fetch_precio_spot(engine, date_from, date_to, result, progress):
    progress("Descargando precio spot ADME...", 0.32)
    t0 = time.time()
    try:
        conn     = AdmePrecioSpotConnector()
        df_raw   = conn.fetch(date_from, date_to)
        df_clean = clean_spot_price(df_raw)
        upsert_dataframe(engine, spot_price, df_clean)
        log_ingestion(engine, "adme_precio_spot", "spot_price_usd",
                      date_from.isoformat(), date_to.isoformat(),
                      len(df_raw), len(df_clean), "success",
                      duration_sec=time.time() - t0)
        progress("Precio spot: OK.", 0.45)
    except Exception as exc:
        result.errors.append(f"Precio spot: {exc}")
        logger.error("Precio Spot falló: %s", exc)


def _build_charts(engine, date_from, date_to, label, result):
    src = "Fuente: ADME / UTE"

    for name, fn, kwargs in [
        ("donut", chart_generation_donut, dict(
            df_mix=result.mix,
            title="Composición de la matriz eléctrica",
            subtitle=label, date_label=f"Período: {label}", source_label=src,
        )),
        ("area", chart_generation_area, dict(
            df=result.df_gen,
            title="Mix de generación eléctrica — Uruguay",
            subtitle=label, date_label=f"Período: {label}", source_label=src,
        )),
    ]:
        try:
            result.charts[name] = fn(**kwargs)
        except Exception as exc:
            result.errors.append(f"Gráfico {name}: {exc}")

    # Barras y YoY requieren monthly_summary
    try:
        df_monthly = monthly_summary(result.df_gen)

        try:
            df_prev = query_generation_daily(
                engine,
                date_from.replace(year=date_from.year - 1).isoformat(),
                date_to.replace(year=date_to.year - 1).isoformat(),
            )
            df_yoy = (
                monthly_summary(pd.concat([result.df_gen, df_prev], ignore_index=True))
                if not df_prev.empty else df_monthly
            )
        except Exception:
            df_yoy = df_monthly

        result.charts["bar"] = chart_renewables_vs_nonrenewables(
            df_monthly,
            title="Renovable vs. no renovable",
            subtitle=label, date_label=f"Período: {label}", source_label=src,
        )
        result.charts["yoy"] = chart_yoy_comparison(
            df_yoy,
            year_current=date_to.year,
            year_previous=date_to.year - 1,
            title="Comparativa interanual",
            subtitle=label, date_label=f"Período: {label}", source_label=src,
        )
    except Exception as exc:
        result.errors.append(f"Gráficos barras/YoY: {exc}")

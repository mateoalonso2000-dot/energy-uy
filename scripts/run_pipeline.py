"""
run_pipeline.py — Entry point principal del pipeline energy-uy.

Orquesta los módulos A → B → C → D → E → F en secuencia:
    A. Adquisición (conectores)
    B. Procesamiento y limpieza
    C. Almacenamiento en SQLite
    D. Análisis e indicadores
    E. Visualización (5 gráficos)
    F. Generación de contenido editorial

Uso básico:
    python scripts/run_pipeline.py --date-from 2024-01-01 --date-to 2024-01-31

Flags opcionales:
    --source        adme_scada | ute_bajadas | adme_panel | all (default: all)
    --skip-fetch    usar datos ya en DB, omitir descarga
    --period        daily | weekly | monthly (default: monthly) — granularidad del reporte
    --output-dir    sobreescribir directorio de salida del config
"""

import argparse
import logging
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

# Asegurar que la raíz del proyecto esté en el path
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from src.connectors.adme_scada import AdmeScadaConnector
from src.connectors.adme_generacion_mensual import AdmeGeneracionMensualConnector
from src.connectors.adme_precio_spot import AdmePrecioSpotConnector
from src.connectors.ute_bajadas import UteBajadasConnector
from src.processing.cleaner import (
    clean_demand_daily,
    clean_generation_daily,
    clean_generation_hourly,
    clean_spot_price,
    clean_exchange,
)
from src.processing.transformer import (
    aggregate_hourly_to_daily,
    monthly_summary,
)
from src.storage.database import get_engine, init_db
from src.storage.models import (
    demand_daily,
    exchange,
    generation_daily,
    generation_hourly,
    spot_price,
)
from src.storage.repository import (
    log_ingestion,
    query_demand_daily,
    query_generation_daily,
    query_spot_price,
    upsert_dataframe,
)
from src.analysis.indicators import (
    demand_evolution,
    generation_mix,
    renewable_share,
)
from src.visualization.charts import (
    chart_demand_evolution,
    chart_generation_area,
    chart_generation_donut,
    chart_renewables_vs_nonrenewables,
    chart_yoy_comparison,
)
from src.visualization.exporter import export_all_charts
from src.editorial.findings import build_findings
from src.editorial.renderer import render_linkedin_post


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pipeline de datos del sistema eléctrico uruguayo."
    )
    parser.add_argument(
        "--date-from",
        type=lambda s: date.fromisoformat(s),
        default=date.today().replace(day=1) - timedelta(days=1),
        help="Fecha de inicio (YYYY-MM-DD). Default: primer día del mes anterior.",
    )
    parser.add_argument(
        "--date-to",
        type=lambda s: date.fromisoformat(s),
        default=date.today() - timedelta(days=1),
        help="Fecha de fin (YYYY-MM-DD). Default: ayer.",
    )
    parser.add_argument(
        "--source",
        choices=["adme_scada", "ute_bajadas", "adme_panel", "all"],
        default="all",
        help="Fuente(s) a descargar. Default: all.",
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Omitir la descarga y usar datos ya almacenados en la DB.",
    )
    parser.add_argument(
        "--period",
        choices=["daily", "weekly", "monthly"],
        default="monthly",
        help="Granularidad del reporte editorial. Default: monthly.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directorio de salida para gráficos y reportes.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(config.LOG_LEVEL)
    logger = logging.getLogger("pipeline")

    logger.info("=" * 60)
    logger.info("energy-uy pipeline  |  %s → %s", args.date_from, args.date_to)
    logger.info("=" * 60)

    # ─── Inicializar base de datos ────────────────────────────────────────────
    engine = get_engine(config.DB_PATH)
    init_db(engine)

    output_dir = args.output_dir or config.OUTPUT_DIR
    date_slug  = f"{args.date_from}_{args.date_to}"

    # ─── MÓDULO A + B + C: Adquisición, limpieza y almacenamiento ────────────
    if not args.skip_fetch:
        _run_fetch(engine, args)
    else:
        logger.info("--skip-fetch activo: omitiendo descarga de datos.")

    # ─── MÓDULO D: Análisis ───────────────────────────────────────────────────
    logger.info("Módulo D: análisis de indicadores...")

    df_gen = query_generation_daily(
        engine,
        args.date_from.isoformat(),
        args.date_to.isoformat(),
    )
    df_demand = query_demand_daily(
        engine,
        args.date_from.isoformat(),
        args.date_to.isoformat(),
    )
    df_price = query_spot_price(
        engine,
        args.date_from.isoformat(),
        args.date_to.isoformat(),
        granularity="daily",
    )

    if df_gen.empty:
        logger.warning(
            "No hay datos de generación en la DB para el período solicitado. "
            "Ejecutar sin --skip-fetch o verificar las fuentes."
        )
        return

    df_demand_evol = demand_evolution(df_demand) if not df_demand.empty else df_demand
    df_monthly     = monthly_summary(df_gen)

    # Para el gráfico interanual, combinar datos del período actual y el mismo
    # período del año anterior (si existen en la DB).
    try:
        date_prev_from = args.date_from.replace(year=args.date_from.year - 1)
        date_prev_to   = args.date_to.replace(year=args.date_to.year - 1)
    except ValueError:
        # edge case: 29-Feb en año bisiesto
        import calendar
        date_prev_from = args.date_from.replace(year=args.date_from.year - 1, day=28)
        date_prev_to   = args.date_to.replace(year=args.date_to.year - 1, day=28)

    df_gen_prev = query_generation_daily(
        engine,
        date_prev_from.isoformat(),
        date_prev_to.isoformat(),
    )
    if not df_gen_prev.empty:
        import pandas as _pd
        df_monthly_yoy = monthly_summary(_pd.concat([df_gen, df_gen_prev], ignore_index=True))
        logger.info("Gráfico interanual: %d filas año actual + %d filas año anterior.",
                    len(df_gen), len(df_gen_prev))
    else:
        df_monthly_yoy = df_monthly
        logger.info("Gráfico interanual: sin datos del año anterior en la DB.")

    # ─── MÓDULO E: Visualización ──────────────────────────────────────────────
    logger.info("Módulo E: generando gráficos...")

    period_label = _period_label(args.date_from, args.date_to)
    source_label = "Fuente: ADME / UTE"

    charts = {}

    if not df_gen.empty:
        charts["mix_generacion_area"] = chart_generation_area(
            df_gen,
            title="Mix de generación eléctrica — Uruguay",
            subtitle=period_label,
            date_label=f"Período: {period_label}",
            source_label=source_label,
        )

        mix = generation_mix(df_gen)
        charts["mix_generacion_donut"] = chart_generation_donut(
            mix,
            title="Composición de la matriz eléctrica",
            subtitle=period_label,
            date_label=f"Período: {period_label}",
            source_label=source_label,
        )

        charts["renovables_barras"] = chart_renewables_vs_nonrenewables(
            df_monthly,
            title="Generación renovable vs. no renovable",
            subtitle=period_label,
            date_label=f"Período: {period_label}",
            source_label=source_label,
        )

        charts["comparativa_interanual"] = chart_yoy_comparison(
            df_monthly_yoy,
            year_current=args.date_to.year,
            year_previous=args.date_to.year - 1,
            title="Comparativa interanual de generación",
            subtitle=period_label,
            date_label=f"Período: {period_label}",
            source_label=source_label,
        )

    if not df_demand_evol.empty:
        charts["demanda_evolucion"] = chart_demand_evolution(
            df_demand_evol,
            title="Evolución de la demanda eléctrica — Uruguay",
            subtitle=period_label,
            date_label=f"Período: {period_label}",
            source_label="Fuente: UTE",
        )

    chart_paths = export_all_charts(charts, output_dir / "charts", date_slug)
    logger.info("Gráficos exportados en: %s", output_dir / "charts" / date_slug)

    # ─── MÓDULO F: Editorial ──────────────────────────────────────────────────
    logger.info("Módulo F: generando reporte editorial...")

    findings = build_findings(
        df_gen=df_gen,
        period_label=period_label,
        df_demand=df_demand_evol if not df_demand_evol.empty else None,
        df_price=df_price if not df_price.empty else None,
    )

    report_path = output_dir / "reports" / date_slug / "reporte_linkedin.txt"
    rendered    = render_linkedin_post(findings, report_path)

    logger.info("Reporte editorial guardado en: %s", report_path)

    # ─── Resumen final ────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("Pipeline completado.")
    logger.info("Gráficos:  %s", output_dir / "charts" / date_slug)
    logger.info("Reporte:   %s", report_path)
    logger.info("=" * 60)

    # Mostrar preview del reporte en consola
    # Escribir directo al buffer para evitar UnicodeEncodeError en Windows (cp1252)
    _preview = ("\n" + "─" * 60 + "\n" + rendered + "\n").encode("utf-8")
    sys.stdout.buffer.write(_preview)
    sys.stdout.buffer.flush()


def _run_fetch(engine, args) -> None:
    """Ejecuta la adquisición de datos de todas las fuentes configuradas."""
    logger = logging.getLogger("pipeline.fetch")
    run_adme   = args.source in ("adme_scada", "all")
    run_ute    = args.source in ("ute_bajadas", "all")
    run_panel  = args.source in ("adme_panel", "all")

    # ── ADME SCADA ────────────────────────────────────────────────────────────
    if run_adme:
        logger.info("Fuente: ADME SCADA")
        t0 = time.time()
        try:
            connector = AdmeScadaConnector()
            df_raw    = connector.fetch(args.date_from, args.date_to)
            df_clean  = clean_generation_hourly(df_raw)

            inserted = upsert_dataframe(engine, generation_hourly, df_clean)

            # También agregar a daily para análisis
            df_daily = aggregate_hourly_to_daily(df_clean)
            df_daily["data_source"] = "adme_scada"
            upsert_dataframe(engine, generation_daily, df_daily)

            log_ingestion(
                engine, "adme_scada", "generation_hourly",
                args.date_from.isoformat(), args.date_to.isoformat(),
                len(df_raw), inserted, "success",
                duration_sec=time.time() - t0,
            )
        except Exception as exc:
            logger.error("ADME SCADA falló: %s", exc)
            log_ingestion(
                engine, "adme_scada", "generation_hourly",
                args.date_from.isoformat(), args.date_to.isoformat(),
                0, 0, "error", str(exc), time.time() - t0,
            )

    # ── UTE Bajadas ───────────────────────────────────────────────────────────
    if run_ute and not config.UTE_BAJADAS_ENABLED and args.source != "ute_bajadas":
        logger.warning(
            "UTE Bajadas omitida (UTE_BAJADAS_ENABLED=false en .env). "
            "Para forzar la descarga igual: --source ute_bajadas"
        )
        run_ute = False

    if run_ute:
        ute_datasets = [
            ("COMPOSICION_FUENTE", "generation"),
            ("DEMANDA_MIN_MAX",    "demand"),
            ("INTERCAMBIOS",       "exchange"),
        ]
        for dataset_key, dataset_type in ute_datasets:
            logger.info("Fuente: UTE Bajadas [%s]", dataset_key)
            t0 = time.time()
            try:
                connector = UteBajadasConnector(dataset_key=dataset_key)
                df_raw    = connector.fetch(args.date_from, args.date_to)

                if dataset_type == "generation":
                    df_clean  = clean_generation_daily(df_raw)
                    inserted  = upsert_dataframe(engine, generation_daily, df_clean)
                elif dataset_type == "demand":
                    df_clean  = clean_demand_daily(df_raw)
                    inserted  = upsert_dataframe(engine, demand_daily, df_clean)
                else:
                    df_clean  = clean_exchange(df_raw)
                    inserted  = upsert_dataframe(engine, exchange, df_clean)

                log_ingestion(
                    engine, "ute_bajadas", dataset_key,
                    args.date_from.isoformat(), args.date_to.isoformat(),
                    len(df_raw), inserted, "success", duration_sec=time.time() - t0,
                )
            except Exception as exc:
                logger.error("UTE Bajadas [%s] falló: %s", dataset_key, exc)
                log_ingestion(
                    engine, "ute_bajadas", dataset_key,
                    args.date_from.isoformat(), args.date_to.isoformat(),
                    0, 0, "error", str(exc), time.time() - t0,
                )

    # ── ADME Precio Spot ──────────────────────────────────────────────────────
    if run_panel:
        logger.info("Fuente: ADME Precio Spot")
        t0 = time.time()
        try:
            connector = AdmePrecioSpotConnector()
            df_raw    = connector.fetch(args.date_from, args.date_to)
            df_clean  = clean_spot_price(df_raw)
            inserted  = upsert_dataframe(engine, spot_price, df_clean)

            log_ingestion(
                engine, "adme_precio_spot", "spot_price_usd",
                args.date_from.isoformat(), args.date_to.isoformat(),
                len(df_raw), inserted, "success", duration_sec=time.time() - t0,
            )
        except Exception as exc:
            logger.error("ADME Precio Spot falló: %s", exc)
            log_ingestion(
                engine, "adme_precio_spot", "spot_price_usd",
                args.date_from.isoformat(), args.date_to.isoformat(),
                0, 0, "error", str(exc), time.time() - t0,
            )


def _period_label(date_from: date, date_to: date) -> str:
    """Genera una etiqueta legible del período."""
    MONTHS_ES = {
        1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
        5: "mayo",  6: "junio",  7: "julio",  8: "agosto",
        9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
    }
    if date_from.year == date_to.year and date_from.month == date_to.month:
        return f"{MONTHS_ES[date_from.month]} {date_from.year}"
    return f"{date_from.strftime('%d/%m/%Y')} al {date_to.strftime('%d/%m/%Y')}"


if __name__ == "__main__":
    main()

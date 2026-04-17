"""
repository.py — Funciones de lectura y escritura sobre la base de datos.

Toda interacción con la DB pasa por este módulo. Los módulos de análisis
y visualización solo leen a través de las funciones query_* definidas aquí.
"""

import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy.engine import Engine
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.storage.models import (
    demand_daily,
    exchange,
    generation_daily,
    generation_hourly,
    ingestion_log,
    spot_price,
)

logger = logging.getLogger(__name__)


# ─── Escritura (upsert) ───────────────────────────────────────────────────────

def upsert_dataframe(engine: Engine, table, df: pd.DataFrame) -> int:
    """
    Inserta filas de un DataFrame en la tabla indicada.
    Si ya existe un registro con la misma clave única, lo omite (INSERT OR IGNORE).

    Retorna la cantidad de filas efectivamente insertadas.
    """
    if df.empty:
        logger.warning("DataFrame vacío, nada que insertar en '%s'.", table.name)
        return 0

    records = df.to_dict(orient="records")
    inserted = 0

    with engine.begin() as conn:
        for record in records:
            stmt = sqlite_insert(table).values(**record).prefix_with("OR IGNORE")
            result = conn.execute(stmt)
            inserted += result.rowcount

    logger.info("Tabla '%s': %d/%d filas insertadas.", table.name, inserted, len(records))
    return inserted


def log_ingestion(
    engine: Engine,
    source_name: str,
    dataset: str,
    date_from: str | None,
    date_to: str | None,
    records_fetched: int,
    records_inserted: int,
    status: str,
    error_message: str | None = None,
    duration_sec: float | None = None,
) -> None:
    """Registra el resultado de una ingesta en ingestion_log."""
    with engine.begin() as conn:
        conn.execute(
            ingestion_log.insert().values(
                run_at=datetime.now(timezone.utc).isoformat(),
                source_name=source_name,
                dataset=dataset,
                date_from=date_from,
                date_to=date_to,
                records_fetched=records_fetched,
                records_inserted=records_inserted,
                status=status,
                error_message=error_message,
                duration_sec=duration_sec,
            )
        )


# ─── Lectura ──────────────────────────────────────────────────────────────────

def query_generation_daily(
    engine: Engine,
    date_from: str,
    date_to: str,
    sources: list[str] | None = None,
) -> pd.DataFrame:
    """
    Retorna generación diaria en el rango de fechas indicado.

    Args:
        date_from: fecha inicio en formato 'YYYY-MM-DD'
        date_to:   fecha fin en formato 'YYYY-MM-DD'
        sources:   lista de fuentes a filtrar, ej: ['wind', 'solar']
                   Si es None, retorna todas.
    """
    query = (
        f"SELECT date, source, source_type, SUM(value_mwh) as value_mwh "
        f"FROM generation_daily "
        f"WHERE date BETWEEN :d_from AND :d_to "
    )
    params: dict[str, Any] = {"d_from": date_from, "d_to": date_to}

    if sources:
        placeholders = ", ".join(f":s{i}" for i in range(len(sources)))
        query += f"AND source IN ({placeholders}) "
        params.update({f"s{i}": s for i, s in enumerate(sources)})

    query += "GROUP BY date, source, source_type ORDER BY date, source"

    with engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


def query_generation_hourly(
    engine: Engine,
    date_from: str,
    date_to: str,
) -> pd.DataFrame:
    """Retorna generación horaria en el rango indicado."""
    query = (
        "SELECT timestamp, source, source_type, SUM(value_mw) as value_mw "
        "FROM generation_hourly "
        "WHERE timestamp BETWEEN :d_from AND :d_to "
        "GROUP BY timestamp, source, source_type "
        "ORDER BY timestamp, source"
    )
    with engine.connect() as conn:
        return pd.read_sql_query(
            query, conn, params={"d_from": date_from, "d_to": date_to}
        )


def query_demand_daily(
    engine: Engine,
    date_from: str,
    date_to: str,
) -> pd.DataFrame:
    """Retorna demanda diaria en el rango indicado."""
    query = (
        "SELECT date, value_mwh, min_mw, max_mw "
        "FROM demand_daily "
        "WHERE date BETWEEN :d_from AND :d_to "
        "ORDER BY date"
    )
    with engine.connect() as conn:
        return pd.read_sql_query(
            query, conn, params={"d_from": date_from, "d_to": date_to}
        )


def query_spot_price(
    engine: Engine,
    date_from: str,
    date_to: str,
    granularity: str = "daily",
) -> pd.DataFrame:
    """Retorna precios spot en el rango indicado."""
    query = (
        "SELECT timestamp, granularity, price_usd, price_uyu "
        "FROM spot_price "
        "WHERE timestamp BETWEEN :d_from AND :d_to "
        "AND granularity = :gran "
        "ORDER BY timestamp"
    )
    with engine.connect() as conn:
        return pd.read_sql_query(
            query, conn, params={"d_from": date_from, "d_to": date_to, "gran": granularity}
        )


def query_last_ingestion(engine: Engine, source_name: str) -> dict | None:
    """Retorna el último registro de ingesta exitosa para una fuente dada."""
    query = (
        "SELECT * FROM ingestion_log "
        "WHERE source_name = :src AND status = 'success' "
        "ORDER BY run_at DESC LIMIT 1"
    )
    with engine.connect() as conn:
        result = conn.execute(
            ingestion_log.select()
            .where(ingestion_log.c.source_name == source_name)
            .where(ingestion_log.c.status == "success")
            .order_by(ingestion_log.c.run_at.desc())
            .limit(1)
        ).fetchone()
    return dict(result._mapping) if result else None

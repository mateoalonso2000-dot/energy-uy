"""
transformer.py — Transformaciones y columnas derivadas sobre datos ya limpios.

Responsabilidades:
- Agregar datos horarios a diarios cuando sea necesario.
- Calcular columnas derivadas (ej: total de generación del día).
- Unificar datasets de distintas fuentes en una vista consistente.
- Preparar DataFrames listos para pasar al módulo de análisis.
"""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def aggregate_hourly_to_daily(df_hourly: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega generación horaria (MW) a generación diaria (MWh).

    Conversión: MWh = MW × 1 hora (datos horarios).
    Suma por día y fuente.

    Args:
        df_hourly: DataFrame de generation_hourly con columnas
                   timestamp, source, source_type, value_mw, data_source

    Returns:
        DataFrame con columnas: date, source, source_type, value_mwh, data_source
    """
    df = df_hourly.copy()
    df["date"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d")
    df["value_mwh"] = df["value_mw"]  # 1 registro = 1 hora → MW ≈ MWh

    df_daily = (
        df.groupby(["date", "source", "source_type", "data_source"], as_index=False)
        ["value_mwh"].sum()
    )

    logger.debug(
        "aggregate_hourly_to_daily: %d filas horarias → %d filas diarias.",
        len(df_hourly),
        len(df_daily),
    )
    return df_daily


def add_renewable_flag(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega columna booleana 'is_renewable' basada en source_type.

    Args:
        df: cualquier DataFrame con columna 'source_type'
    """
    df = df.copy()
    df["is_renewable"] = df["source_type"] == "renewable"
    return df


def pivot_generation_by_source(df: pd.DataFrame, value_col: str = "value_mwh") -> pd.DataFrame:
    """
    Convierte el formato largo (una fila por fuente) a formato ancho
    (una columna por fuente). Útil para cálculos de participación.

    Args:
        df:         DataFrame con columnas date/timestamp, source, value_col
        value_col:  nombre de la columna de valores

    Returns:
        DataFrame con una columna por fuente de energía.
    """
    ts_col = "date" if "date" in df.columns else "timestamp"
    df_pivot = df.pivot_table(
        index=ts_col,
        columns="source",
        values=value_col,
        aggfunc="sum",
        fill_value=0.0,
    )
    df_pivot.columns.name = None
    return df_pivot.reset_index()


def calculate_generation_share(df: pd.DataFrame, value_col: str = "value_mwh") -> pd.DataFrame:
    """
    Calcula la participación porcentual de cada fuente en cada período.

    Args:
        df:        DataFrame en formato largo con columnas date/timestamp, source, value_col
        value_col: columna de valores

    Returns:
        DataFrame original con columna adicional 'share_pct' (0–100).
    """
    df = df.copy()
    ts_col = "date" if "date" in df.columns else "timestamp"

    total_by_period = df.groupby(ts_col)[value_col].transform("sum")
    df["share_pct"] = (df[value_col] / total_by_period * 100).round(2)
    df.loc[total_by_period == 0, "share_pct"] = 0.0

    return df


def monthly_summary(df_daily: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega generación diaria a totales mensuales.

    Args:
        df_daily: DataFrame con columnas date, source, source_type, value_mwh

    Returns:
        DataFrame con columnas: year_month (str "YYYY-MM"), source, source_type, value_mwh
    """
    df = df_daily.copy()
    df["year_month"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
    df_monthly = (
        df.groupby(["year_month", "source", "source_type"], as_index=False)
        ["value_mwh"].sum()
    )
    logger.debug("monthly_summary: %d filas diarias → %d filas mensuales.", len(df_daily), len(df_monthly))
    return df_monthly


def merge_generation_and_demand(
    df_gen: pd.DataFrame,
    df_demand: pd.DataFrame,
) -> pd.DataFrame:
    """
    Combina generación diaria con demanda diaria en un único DataFrame.

    Retorna columnas:
        date, source, source_type, value_mwh, share_pct,
        demand_mwh, demand_min_mw, demand_max_mw
    """
    df_gen = calculate_generation_share(df_gen)

    df_demand_clean = df_demand.rename(
        columns={
            "value_mwh": "demand_mwh",
            "min_mw":    "demand_min_mw",
            "max_mw":    "demand_max_mw",
        }
    )[["date", "demand_mwh", "demand_min_mw", "demand_max_mw"]]

    df_merged = df_gen.merge(df_demand_clean, on="date", how="left")
    logger.debug("merge_generation_and_demand: %d filas.", len(df_merged))
    return df_merged

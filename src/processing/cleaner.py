"""
cleaner.py — Limpieza y normalización de DataFrames crudos.

Responsabilidades:
- Estandarizar nombres de columnas.
- Normalizar formatos de fecha/hora a ISO8601.
- Eliminar duplicados.
- Manejar valores faltantes (NaN).
- Validar rangos de valores (ej: MW negativos).
"""

import logging

import pandas as pd

from config import SOURCE_NAME_MAP, SOURCE_TYPE_MAP

logger = logging.getLogger(__name__)


def clean_generation_hourly(df: pd.DataFrame) -> pd.DataFrame:
    """
    Limpia un DataFrame de generación horaria (proveniente de ADME SCADA).

    Operaciones aplicadas:
    1. Normaliza timestamp a ISO8601.
    2. Normaliza nombres de fuente al vocabulario canónico.
    3. Asigna source_type si falta.
    4. Elimina filas con MW negativos (posibles errores de medición).
    5. Elimina duplicados exactos.
    6. Ordena por timestamp y fuente.

    Returns:
        DataFrame limpio con columnas:
        timestamp, source, source_type, plant_name, value_mw, data_source
    """
    df = df.copy()

    # 1. Timestamp
    df["timestamp"] = _normalize_timestamp(df["timestamp"], include_time=True)
    df = df.dropna(subset=["timestamp"])

    # 2. Nombres de fuente
    df["source"] = _normalize_source(df["source"])

    # 3. source_type
    if "source_type" not in df.columns or df["source_type"].isna().any():
        df["source_type"] = df["source"].map(SOURCE_TYPE_MAP).fillna("unknown")

    # 4. plant_name
    if "plant_name" not in df.columns:
        df["plant_name"] = None

    # 5. Valores
    df["value_mw"] = pd.to_numeric(df["value_mw"], errors="coerce")
    n_negative = (df["value_mw"] < 0).sum()
    if n_negative > 0:
        logger.warning("Generación horaria: %d valores negativos → reemplazados por 0.", n_negative)
        df.loc[df["value_mw"] < 0, "value_mw"] = 0.0
    df = df.dropna(subset=["value_mw"])

    # 6. Duplicados
    df = _remove_duplicates(df, subset=["timestamp", "source", "plant_name", "data_source"])

    # 7. Orden
    df = df.sort_values(["timestamp", "source"]).reset_index(drop=True)

    logger.debug("clean_generation_hourly: %d filas después de limpieza.", len(df))
    return df[["timestamp", "source", "source_type", "plant_name", "value_mw", "data_source"]]


def clean_generation_daily(df: pd.DataFrame) -> pd.DataFrame:
    """
    Limpia un DataFrame de generación diaria (proveniente de UTE Bajadas).

    Returns:
        DataFrame limpio con columnas:
        date, source, source_type, value_mwh, data_source
    """
    df = df.copy()

    df["date"] = _normalize_timestamp(df["date"], include_time=False)
    df = df.dropna(subset=["date"])
    df["source"] = _normalize_source(df["source"])
    df["source_type"] = df["source"].map(SOURCE_TYPE_MAP).fillna("unknown")
    df["value_mwh"] = pd.to_numeric(df["value_mwh"], errors="coerce")

    n_negative = (df["value_mwh"] < 0).sum()
    if n_negative > 0:
        logger.warning("Generación diaria: %d valores negativos → reemplazados por 0.", n_negative)
        df.loc[df["value_mwh"] < 0, "value_mwh"] = 0.0

    df = df.dropna(subset=["value_mwh"])
    df = _remove_duplicates(df, subset=["date", "source", "data_source"])
    df = df.sort_values(["date", "source"]).reset_index(drop=True)

    logger.debug("clean_generation_daily: %d filas después de limpieza.", len(df))
    return df[["date", "source", "source_type", "value_mwh", "data_source"]]


def clean_demand_daily(df: pd.DataFrame) -> pd.DataFrame:
    """
    Limpia un DataFrame de demanda diaria (proveniente de UTE Bajadas).

    Returns:
        DataFrame limpio con columnas:
        date, value_mwh, min_mw, max_mw, data_source
    """
    df = df.copy()

    df["date"] = _normalize_timestamp(df["date"], include_time=False)
    df = df.dropna(subset=["date"])

    for col in ["value_mwh", "min_mw", "max_mw"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = None

    df = _remove_duplicates(df, subset=["date", "data_source"])
    df = df.sort_values("date").reset_index(drop=True)

    logger.debug("clean_demand_daily: %d filas después de limpieza.", len(df))
    return df[["date", "value_mwh", "min_mw", "max_mw", "data_source"]]


def clean_exchange(df: pd.DataFrame) -> pd.DataFrame:
    """
    Limpia un DataFrame de intercambios internacionales.

    Returns:
        DataFrame limpio con columnas:
        timestamp, granularity, country, direction, value_mw, value_mwh, data_source
    """
    df = df.copy()

    granularity = df["granularity"].iloc[0] if "granularity" in df.columns else "daily"
    include_time = granularity == "hourly"

    ts_col = "timestamp" if "timestamp" in df.columns else "date"
    df["timestamp"] = _normalize_timestamp(df[ts_col], include_time=include_time)
    df = df.dropna(subset=["timestamp"])

    df["granularity"] = granularity
    df["country"] = df["country"].str.lower().str.strip() if "country" in df.columns else "unknown"
    df["direction"] = df["direction"].str.lower().str.strip() if "direction" in df.columns else "unknown"

    for col in ["value_mw", "value_mwh"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = None

    df = _remove_duplicates(df, subset=["timestamp", "granularity", "country", "direction", "data_source"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    return df[["timestamp", "granularity", "country", "direction", "value_mw", "value_mwh", "data_source"]]


def clean_spot_price(df: pd.DataFrame) -> pd.DataFrame:
    """
    Limpia un DataFrame de precios spot (proveniente de ADME Control Panel).

    Returns:
        DataFrame limpio con columnas:
        timestamp, granularity, price_usd, price_uyu, data_source
    """
    df = df.copy()

    granularity = df["granularity"].iloc[0] if "granularity" in df.columns else "daily"
    include_time = granularity == "hourly"

    df["timestamp"] = _normalize_timestamp(df["timestamp"], include_time=include_time)
    df = df.dropna(subset=["timestamp"])
    df["granularity"] = granularity

    for col in ["price_usd", "price_uyu"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = None

    df = _remove_duplicates(df, subset=["timestamp", "granularity", "data_source"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    return df[["timestamp", "granularity", "price_usd", "price_uyu", "data_source"]]


# ─── Helpers privados ─────────────────────────────────────────────────────────

def _normalize_timestamp(series: pd.Series, include_time: bool = True) -> pd.Series:
    """
    Convierte una serie de fechas/timestamps al formato ISO8601 string.
    - include_time=True  → 'YYYY-MM-DDTHH:MM:SS'
    - include_time=False → 'YYYY-MM-DD'
    """
    dt = pd.to_datetime(series, dayfirst=False, errors="coerce")
    if include_time:
        return dt.dt.strftime("%Y-%m-%dT%H:%M:%S")
    return dt.dt.strftime("%Y-%m-%d")


def _normalize_source(series: pd.Series) -> pd.Series:
    """
    Normaliza nombres de fuentes al vocabulario canónico definido en config.py.
    Ej: 'Eólica' → 'wind', 'Térmica' → 'thermal'
    """
    return (
        series
        .str.lower()
        .str.strip()
        .map(SOURCE_NAME_MAP)
        .fillna(series.str.lower().str.strip())
    )


def _remove_duplicates(df: pd.DataFrame, subset: list[str]) -> pd.DataFrame:
    """
    Elimina filas duplicadas manteniendo la primera ocurrencia.
    Filtra solo las columnas del subset que existen en el DataFrame.
    """
    valid_subset = [c for c in subset if c in df.columns]
    n_before = len(df)
    df = df.drop_duplicates(subset=valid_subset, keep="first")
    n_removed = n_before - len(df)
    if n_removed > 0:
        logger.debug("_remove_duplicates: %d duplicados eliminados.", n_removed)
    return df

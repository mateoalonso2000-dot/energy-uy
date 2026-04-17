"""
indicators.py — Cálculo de indicadores del sistema eléctrico.

Todas las funciones reciben DataFrames ya limpios (output del módulo processing)
y retornan estructuras simples (dict o DataFrame) listas para visualización
o generación de contenido editorial.
"""

import logging
from datetime import date, timedelta

import pandas as pd

logger = logging.getLogger(__name__)


def generation_mix(df_gen: pd.DataFrame, value_col: str = "value_mwh") -> pd.DataFrame:
    """
    Calcula la participación porcentual de cada fuente en el período.

    Args:
        df_gen:    DataFrame con columnas source, value_col (en formato largo)
        value_col: columna de valores energéticos

    Returns:
        DataFrame con columnas: source, source_type, total_mwh, share_pct
        ordenado de mayor a menor participación.
    """
    summary = (
        df_gen.groupby(["source", "source_type"])[value_col]
        .sum()
        .reset_index()
        .rename(columns={value_col: "total_mwh"})
    )
    total = summary["total_mwh"].sum()
    summary["share_pct"] = (summary["total_mwh"] / total * 100).round(2) if total > 0 else 0.0
    summary = summary.sort_values("share_pct", ascending=False).reset_index(drop=True)

    logger.debug("generation_mix: %d fuentes analizadas. Total: %.0f MWh.", len(summary), total)
    return summary


def renewable_share(df_gen: pd.DataFrame, value_col: str = "value_mwh") -> dict:
    """
    Calcula el porcentaje de generación renovable sobre el total.

    Returns:
        dict con claves:
        - renewable_mwh: energía renovable total
        - non_renewable_mwh: energía no renovable total
        - total_mwh: total generado
        - renewable_pct: porcentaje renovable (0–100)
    """
    df = df_gen.copy()
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce").fillna(0)

    renewable = df[df["source_type"] == "renewable"][value_col].sum()
    non_renewable = df[df["source_type"] == "non_renewable"][value_col].sum()
    total = renewable + non_renewable

    return {
        "renewable_mwh":     round(renewable, 1),
        "non_renewable_mwh": round(non_renewable, 1),
        "total_mwh":         round(total, 1),
        "renewable_pct":     round(renewable / total * 100, 2) if total > 0 else 0.0,
    }


def demand_evolution(df_demand: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula variación porcentual diaria y media móvil de 7 días de la demanda.

    Args:
        df_demand: DataFrame con columnas date (str), value_mwh (float)

    Returns:
        DataFrame con columnas adicionales:
        - delta_pct:   variación % respecto al día anterior
        - ma_7d:       media móvil de 7 días
        - ma_30d:      media móvil de 30 días
    """
    df = df_demand.copy().sort_values("date").reset_index(drop=True)
    df["value_mwh"] = pd.to_numeric(df["value_mwh"], errors="coerce")
    df["delta_pct"] = df["value_mwh"].pct_change() * 100
    df["ma_7d"]  = df["value_mwh"].rolling(7,  min_periods=1).mean()
    df["ma_30d"] = df["value_mwh"].rolling(30, min_periods=1).mean()
    return df


def period_comparison(
    df_gen: pd.DataFrame,
    period_a_from: str,
    period_a_to: str,
    period_b_from: str,
    period_b_to: str,
    value_col: str = "value_mwh",
) -> pd.DataFrame:
    """
    Compara el mix de generación entre dos períodos.

    Returns:
        DataFrame con columnas:
        source, total_a, share_a_pct, total_b, share_b_pct, delta_pp
        (delta_pp = diferencia en puntos porcentuales entre períodos)
    """
    def summarize(df_filtered):
        s = df_filtered.groupby("source")[value_col].sum().reset_index()
        total = s[value_col].sum()
        s["share_pct"] = (s[value_col] / total * 100).round(2) if total > 0 else 0.0
        return s

    df_a = df_gen[(df_gen["date"] >= period_a_from) & (df_gen["date"] <= period_a_to)]
    df_b = df_gen[(df_gen["date"] >= period_b_from) & (df_gen["date"] <= period_b_to)]

    s_a = summarize(df_a).rename(columns={value_col: "total_a", "share_pct": "share_a_pct"})
    s_b = summarize(df_b).rename(columns={value_col: "total_b", "share_pct": "share_b_pct"})

    result = s_a.merge(s_b, on="source", how="outer").fillna(0)
    result["delta_pp"] = (result["share_b_pct"] - result["share_a_pct"]).round(2)
    return result.sort_values("share_b_pct", ascending=False).reset_index(drop=True)


def detect_anomalies(df: pd.DataFrame, value_col: str, z_threshold: float = 2.0) -> pd.DataFrame:
    """
    Marca registros cuyo valor supera z_threshold desviaciones estándar
    respecto a la media histórica del DataFrame.

    Stub simplificado para el MVP: z-score sobre el período completo.
    No usa modelos de series de tiempo ni ventanas estacionales.

    Returns:
        DataFrame original con columnas adicionales:
        - z_score:    desviación estándar normalizada
        - is_anomaly: True si |z_score| > z_threshold
    """
    df = df.copy()
    col = pd.to_numeric(df[value_col], errors="coerce")
    mean = col.mean()
    std  = col.std()

    df["z_score"]    = ((col - mean) / std).round(3) if std > 0 else 0.0
    df["is_anomaly"] = df["z_score"].abs() > z_threshold

    n_anomalies = df["is_anomaly"].sum()
    if n_anomalies > 0:
        logger.info("detect_anomalies: %d registros anómalos detectados (z > %.1f).", n_anomalies, z_threshold)

    return df


def monthly_summary(df_gen: pd.DataFrame, value_col: str = "value_mwh") -> pd.DataFrame:
    """
    Agrega generación por mes y fuente.

    Returns:
        DataFrame con columnas: year_month (str 'YYYY-MM'), source, source_type, value_mwh
    """
    df = df_gen.copy()
    df["year_month"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
    return (
        df.groupby(["year_month", "source", "source_type"])[value_col]
        .sum()
        .reset_index()
        .sort_values(["year_month", "source"])
        .reset_index(drop=True)
    )


def leading_source(df_mix: pd.DataFrame) -> dict:
    """
    Retorna la fuente con mayor participación en el período.

    Args:
        df_mix: output de generation_mix()

    Returns:
        dict con source, share_pct, total_mwh
    """
    top = df_mix.iloc[0]
    return {
        "source":     top["source"],
        "share_pct":  top["share_pct"],
        "total_mwh":  top["total_mwh"],
    }

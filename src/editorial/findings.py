"""
findings.py — Generación automática de hallazgos e insights del sistema eléctrico.

Transforma indicadores numéricos en frases interpretables para audiencias
profesionales no especializadas. Tono: analítico, sobrio, sin exageraciones.
"""

import logging
from dataclasses import dataclass, field

import pandas as pd

from src.analysis.indicators import (
    detect_anomalies,
    generation_mix,
    leading_source,
    renewable_share,
)

logger = logging.getLogger(__name__)

# Nombres en español para los textos generados
SOURCE_NAMES_ES = {
    "wind":     "energía eólica",
    "solar":    "energía solar",
    "hydro":    "generación hidráulica",
    "biomass":  "biomasa",
    "thermal":  "generación térmica",
    "import":   "importación",
    "export":   "exportación",
}


@dataclass
class PeriodFindings:
    """Contenedor de todos los hallazgos para un período dado."""
    period_label: str                   # ej: "enero 2024" o "semana del 15 al 21 de enero"
    leading_source_text: str = ""
    renewable_text: str = ""
    demand_text: str = ""
    price_text: str = ""
    anomaly_text: str = ""
    comparison_text: str = ""
    bullets: list[str] = field(default_factory=list)
    # Campos numéricos para que el renderer construya frases contextuales
    renewable_pct: float = 0.0
    top_source: str = ""
    top_source_pct: float = 0.0


def build_findings(
    df_gen: pd.DataFrame,
    period_label: str,
    df_demand: pd.DataFrame | None = None,
    df_price: pd.DataFrame | None = None,
    df_gen_prev: pd.DataFrame | None = None,
    period_prev_label: str = "",
) -> PeriodFindings:
    """
    Genera el conjunto de hallazgos para un período.

    Args:
        df_gen:         generación del período actual (formato largo, daily)
        period_label:   descripción del período (ej: "enero 2024")
        df_demand:      demanda del período (opcional)
        df_price:       precios spot del período (opcional)
        df_gen_prev:    generación del período anterior para comparación (opcional)
        period_prev_label: descripción del período anterior

    Returns:
        PeriodFindings con todos los hallazgos populados.
    """
    findings = PeriodFindings(period_label=period_label)

    # ── Mix y fuente líder ────────────────────────────────────────────────────
    mix = generation_mix(df_gen)
    if not mix.empty:
        top = leading_source(mix)
        source_name = SOURCE_NAMES_ES.get(top["source"], top["source"])
        findings.leading_source_text = (
            f"La {source_name} lideró la generación durante {period_label}, "
            f"representando el {top['share_pct']:.1f}% de la matriz eléctrica "
            f"({top['total_mwh']:,.0f} MWh)."
        )
        findings.top_source     = top["source"]
        findings.top_source_pct = top["share_pct"]

    # ── Renovables ────────────────────────────────────────────────────────────
    ren = renewable_share(df_gen)
    findings.renewable_pct = ren["renewable_pct"]
    if ren["total_mwh"] > 0:
        findings.renewable_text = (
            f"Las fuentes renovables explicaron el {ren['renewable_pct']:.1f}% "
            f"de la generación en {period_label} "
            f"({ren['renewable_mwh']:,.0f} MWh de {ren['total_mwh']:,.0f} MWh totales)."
        )

    # ── Demanda ───────────────────────────────────────────────────────────────
    if df_demand is not None and not df_demand.empty and "delta_pct" in df_demand.columns:
        last_delta = df_demand["delta_pct"].dropna().iloc[-1] if not df_demand["delta_pct"].dropna().empty else None
        if last_delta is not None:
            direction = "aumentó" if last_delta >= 0 else "disminuyó"
            findings.demand_text = (
                f"La demanda {direction} un {abs(last_delta):.1f}% "
                f"respecto al día anterior al cierre del período."
            )

    # ── Precio spot ───────────────────────────────────────────────────────────
    if df_price is not None and not df_price.empty:
        price_col = "price_usd" if "price_usd" in df_price.columns else "price_uyu"
        currency  = "USD" if price_col == "price_usd" else "UYU"
        avg_price = df_price[price_col].mean()
        findings.price_text = (
            f"El precio spot promedio del período fue {avg_price:.2f} {currency}/MWh."
        )

    # ── Comparación con período anterior ──────────────────────────────────────
    if df_gen_prev is not None and not df_gen_prev.empty and period_prev_label:
        ren_prev = renewable_share(df_gen_prev)
        delta_pp = ren["renewable_pct"] - ren_prev["renewable_pct"]
        direction = "superior" if delta_pp >= 0 else "inferior"
        findings.comparison_text = (
            f"La participación renovable del período fue {abs(delta_pp):.1f} puntos porcentuales "
            f"{direction} a la registrada en {period_prev_label} "
            f"({ren_prev['renewable_pct']:.1f}%)."
        )

    # ── Anomalías en demanda ──────────────────────────────────────────────────
    if df_demand is not None and not df_demand.empty and "value_mwh" in df_demand.columns:
        df_anom = detect_anomalies(df_demand, "value_mwh", z_threshold=2.0)
        n_anom = df_anom["is_anomaly"].sum()
        if n_anom > 0:
            findings.anomaly_text = (
                f"Se detectaron {n_anom} día(s) con demanda atípica "
                f"(desvío superior a 2σ respecto al promedio del período)."
            )

    # ── Bullets consolidados ──────────────────────────────────────────────────
    findings.bullets = _build_bullets(findings, mix)

    return findings


def _build_bullets(findings: PeriodFindings, mix: pd.DataFrame) -> list[str]:
    """
    Arma la lista de bullets a partir de los hallazgos individuales.
    Se incluyen solo los que tienen contenido. Máximo 5 bullets.
    """
    bullets = []

    if findings.leading_source_text:
        bullets.append(findings.leading_source_text)

    if findings.renewable_text:
        bullets.append(findings.renewable_text)

    if findings.comparison_text:
        bullets.append(findings.comparison_text)

    if findings.demand_text:
        bullets.append(findings.demand_text)

    if findings.price_text:
        bullets.append(findings.price_text)

    if findings.anomaly_text and len(bullets) < 5:
        bullets.append(findings.anomaly_text)

    # Si hay más de 5, truncar
    return bullets[:5]

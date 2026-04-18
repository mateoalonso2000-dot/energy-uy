"""
renderer.py — Renderiza el reporte editorial y el copy para LinkedIn.

Toma los hallazgos (PeriodFindings) y produce el texto final usando
plantillas Jinja2. El tono es analítico, técnico y sobrio.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from src.editorial.findings import PeriodFindings

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"

SOURCE_NAMES_ES = {
    "wind":     "eólica",
    "solar":    "solar",
    "hydro":    "hidráulica",
    "biomass":  "biomasa",
    "thermal":  "térmica",
}


def render_linkedin_post(
    findings: PeriodFindings,
    output_path: Path,
) -> str:
    """
    Renderiza el reporte completo (título, bullets, copy) y lo guarda en disco.

    Args:
        findings:    objeto PeriodFindings con todos los hallazgos
        output_path: ruta completa del archivo de salida (.txt o .md)

    Returns:
        El texto renderizado como string.
    """
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("linkedin_post.j2")

    title_suggestion = _build_title(findings)
    interpretation   = _build_interpretation(findings)
    linkedin_copy    = _build_copy(findings, title_suggestion, interpretation)

    context = {
        "period_label":     findings.period_label,
        "title_suggestion": title_suggestion,
        "bullets":          findings.bullets,
        "interpretation":   interpretation,
        "linkedin_copy":    linkedin_copy,
        "generated_at":     datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }

    rendered = template.render(**context)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    logger.info("Reporte editorial guardado en: %s", output_path)

    return rendered


def _build_title(findings: PeriodFindings) -> str:
    """
    Genera un título sugerido para el post de LinkedIn.
    Prioriza el hallazgo más llamativo del período.
    """
    if findings.leading_source_text:
        # Extraer nombre de fuente del texto ya generado
        text = findings.leading_source_text
        if "energía eólica" in text:
            source = "la energía eólica"
        elif "energía solar" in text:
            source = "la energía solar"
        elif "generación hidráulica" in text:
            source = "la hidráulica"
        elif "biomasa" in text:
            source = "la biomasa"
        elif "generación térmica" in text:
            source = "la generación térmica"
        else:
            source = "las fuentes renovables"

        return f"Sistema eléctrico uruguayo en {findings.period_label}: {source} lideró la matriz"

    if findings.renewable_text:
        return f"Las renovables sostienen la matriz eléctrica de Uruguay en {findings.period_label}"

    return f"Informe del sistema eléctrico uruguayo. {findings.period_label}"


def _build_interpretation(findings: PeriodFindings) -> str:
    """
    Construye una frase de contexto que NO repite los bullets.

    El objetivo es responder al "¿y qué?" — situar el dato en perspectiva
    regional o histórica. Usa los campos numéricos de PeriodFindings para
    construir texto distinto al de los bullets.
    """
    pct = findings.renewable_pct

    # Contexto basado en nivel de penetración renovable
    if pct >= 99:
        context = (
            f"Uruguay alcanza cobertura renovable prácticamente total en {findings.period_label},"
            " un nivel excepcional a escala global que la región tardó décadas en construir."
        )
    elif pct >= 90:
        context = (
            f"Con {pct:.0f}% de generación renovable, Uruguay se posiciona "
            "entre los sistemas eléctricos más limpios de América Latina."
        )
    elif pct >= 70:
        context = (
            f"El {pct:.0f}% de penetración renovable refleja la apuesta estructural "
            "de Uruguay por recursos autóctonos (viento, agua y biomasa),"
            " reduciendo su exposición a los precios de combustibles."
        )
    elif pct >= 50:
        context = (
            f"Las renovables superaron la mitad de la generación ({pct:.0f}%), "
            "aunque la matriz sigue requiriendo respaldo térmico o importaciones en períodos de baja hidrología."
        )
    else:
        context = (
            f"La participación renovable se ubicó en {pct:.0f}%, "
            "por debajo del promedio histórico, señalando mayor dependencia de fuentes convencionales."
        )

    # Si hay comparación interanual, se agrega como segunda oración (no como bullet)
    if findings.comparison_text:
        return f"{context} {findings.comparison_text}"

    # Si hay anomalía en demanda, agregar como dato adicional
    if findings.anomaly_text:
        return f"{context} {findings.anomaly_text}"

    return context


def build_linkedin_copy(findings: PeriodFindings) -> str:
    """
    Función pública: genera el copy completo listo para LinkedIn.
    Combina título, hook, bullets e interpretación en un único string.
    """
    title          = _build_title(findings)
    interpretation = _build_interpretation(findings)
    return _build_copy(findings, title, interpretation)


def _build_copy(findings: PeriodFindings, title: str, interpretation: str) -> str:
    """
    Construye el copy completo listo para pegar en LinkedIn.

    Estructura:
        Hook (pregunta o dato de apertura)
        Título
        [línea en blanco]
        Bullets con ▸
        [línea en blanco]
        Frase de contexto (distinta a los bullets)
        [línea en blanco]
        Atribución de datos
        Hashtags

    Regla de estilo: no usar em dash (—). Es una señal de texto generado por IA.
    Usar coma, punto, dos puntos o paréntesis como alternativa.
    """
    lines = []

    # Hook de apertura — invita a leer antes de mostrar los datos
    hook = _build_hook(findings)
    if hook:
        lines.append(hook)
        lines.append("")

    lines.append(title)
    lines.append("")

    if findings.bullets:
        for bullet in findings.bullets:
            lines.append(f"▸ {bullet}")
        lines.append("")

    # Contexto adicional (no repite bullets)
    if interpretation:
        lines.append(interpretation)
        lines.append("")

    lines.append(
        "Datos: ADME (Administración del Mercado Eléctrico) y UTE. "
        f"Período: {findings.period_label}."
    )
    lines.append("")
    lines.append("#EnergíaUruguay #SistemaEléctrico #Renovables #Energía")

    return "\n".join(lines)


def _build_hook(findings: PeriodFindings) -> str:
    """
    Genera una línea de apertura para captar atención en LinkedIn.
    Basada en el dato más llamativo del período.
    """
    pct = findings.renewable_pct

    if pct >= 99:
        return f"¿Sabías que Uruguay generó prácticamente el 100% de su electricidad con fuentes renovables en {findings.period_label}?"

    if pct >= 90 and findings.top_source == "wind":
        return f"El viento cubrió más de la mitad de la demanda eléctrica uruguaya en {findings.period_label}."

    if pct >= 90 and findings.top_source == "hydro":
        return f"La hidráulica volvió a protagonizar la matriz eléctrica uruguaya en {findings.period_label}."

    if findings.top_source_pct >= 50:
        source_name = SOURCE_NAMES_ES.get(findings.top_source, findings.top_source)
        return f"Una sola fuente explicó más de la mitad de la generación eléctrica uruguaya en {findings.period_label}: la {source_name}."

    if pct >= 70:
        return f"Datos del sistema eléctrico uruguayo para {findings.period_label}:"

    return ""

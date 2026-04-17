"""
charts.py — Visualizaciones interactivas con Plotly.
Paleta AIC Economía & Finanzas: Navy #1D3461 + Verde #27AE60.

Cada función retorna un go.Figure listo para st.plotly_chart().
"""

import pandas as pd
import plotly.graph_objects as go

# ── Paleta AIC + fuentes de energía ──────────────────────────────────────────

COLORS = {
    # Renovables — familia verde AIC
    "hydro":         "#27AE60",   # verde AIC (principal)
    "wind":          "#1D3461",   # navy AIC
    "solar":         "#F0A500",   # ámbar cálido (solar = sol)
    "biomass":       "#1E8449",   # verde oscuro AIC
    # No renovables — tonos neutros/fríos
    "thermal":       "#8896B0",   # slate azul-gris AIC
    "import":        "#3A5A96",   # navy medio AIC
    "export":        "#C0392B",   # rojo apagado
    # Agregados
    "renewable":     "#27AE60",   # verde AIC
    "non_renewable": "#C0392B",   # rojo apagado
    "demand":        "#1D3461",   # navy AIC
}

SOURCE_LABELS = {
    "wind":          "Eólica",
    "solar":         "Solar",
    "hydro":         "Hidráulica",
    "biomass":       "Biomasa",
    "thermal":       "Térmica",
    "import":        "Importación",
    "export":        "Exportación",
    "renewable":     "Renovable",
    "non_renewable": "No renovable",
    "demand":        "Demanda",
}

SOURCE_ORDER = ["hydro", "wind", "solar", "biomass", "thermal", "import", "export"]

NAVY    = "#1D3461"
GREEN   = "#27AE60"
GRID    = "#E8EDF5"
SUBTEXT = "#8896B0"

_HOVER = dict(
    bgcolor="white",
    bordercolor=NAVY,
    font=dict(size=12, family="Inter, sans-serif", color=NAVY),
)


def _footer(source_label: str, date_label: str) -> list:
    parts = [p for p in [source_label, date_label] if p]
    if not parts:
        return []
    return [dict(
        text="  |  ".join(parts),
        x=0, y=-0.14, xref="paper", yref="paper",
        showarrow=False,
        font=dict(size=9, color=SUBTEXT, family="Inter, sans-serif"),
        xanchor="left",
    )]


def _subtitle_ann(subtitle: str) -> list:
    if not subtitle:
        return []
    return [dict(
        text=subtitle,
        x=0.5, y=1.07, xref="paper", yref="paper",
        showarrow=False,
        font=dict(size=11, color=SUBTEXT, family="Inter, sans-serif"),
        xanchor="center",
    )]


# ── Gráfico 1: Donut de composición ──────────────────────────────────────────

def chart_generation_donut(
    df_mix: pd.DataFrame,
    title: str = "Composición de la matriz eléctrica",
    subtitle: str = "",
    date_label: str = "",
    source_label: str = "Fuente: ADME / UTE",
) -> go.Figure:
    """Donut interactivo de participación por fuente."""
    df = df_mix[df_mix["share_pct"] > 0.1].copy()
    ordered = [c for c in SOURCE_ORDER if c in df["source"].values]
    extra   = [c for c in df["source"].values if c not in ordered]
    df = df.set_index("source").reindex(ordered + extra).dropna().reset_index()

    labels = [SOURCE_LABELS.get(s, s.capitalize()) for s in df["source"]]
    colors = [COLORS.get(s, "#CCCCCC") for s in df["source"]]

    # Texto central: % renovable
    ren_pct = 0.0
    if "source_type" in df_mix.columns:
        ren_pct = df_mix[df_mix["source_type"] == "renewable"]["share_pct"].sum()

    fig = go.Figure(go.Pie(
        labels=labels,
        values=df["share_pct"],
        hole=0.54,
        marker=dict(colors=colors, line=dict(color="white", width=2.5)),
        textinfo="label+percent",
        textfont=dict(size=11, family="Inter, sans-serif"),
        hovertemplate="<b>%{label}</b><br>%{value:.1f}%<br>%{customdata:.1f} GWh<extra></extra>",
        customdata=df["total_mwh"] / 1000,
        direction="clockwise",
        sort=False,
    ))

    fig.add_annotation(
        text=(
            f"<b style='font-size:18px'>{ren_pct:.0f}%</b>"
            f"<br><span style='font-size:10px;color:{SUBTEXT}'>renovable</span>"
        ),
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=14, color=NAVY, family="Inter, sans-serif"),
        xanchor="center", yanchor="middle",
    )

    fig.update_layout(
        title=dict(text=title, font=dict(size=15, color=NAVY, family="Inter, sans-serif"), x=0),
        paper_bgcolor="white",
        margin=dict(l=16, r=160, t=56, b=48),
        legend=dict(
            orientation="v", x=1.02, y=0.5,
            font=dict(size=11, family="Inter, sans-serif"),
        ),
        hoverlabel=_HOVER,
        annotations=_subtitle_ann(subtitle) + _footer(source_label, date_label),
        font=dict(family="Inter, sans-serif", color=NAVY),
    )
    return fig


# ── Gráfico 2: Área apilada del mix diario ────────────────────────────────────

def chart_generation_area(
    df: pd.DataFrame,
    title: str = "Mix de generación eléctrica — Uruguay",
    subtitle: str = "",
    date_label: str = "",
    source_label: str = "Fuente: ADME / UTE",
) -> go.Figure:
    """Área apilada interactiva: generación diaria por fuente."""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])

    df_pivot = df.pivot_table(
        index="date", columns="source", values="value_mwh", aggfunc="sum", fill_value=0
    )
    ordered = [c for c in SOURCE_ORDER if c in df_pivot.columns]
    extra   = [c for c in df_pivot.columns if c not in ordered]
    df_pivot = df_pivot[ordered + extra]

    fig = go.Figure()
    for source in df_pivot.columns:
        label = SOURCE_LABELS.get(source, source.capitalize())
        color = COLORS.get(source, "#CCCCCC")
        fig.add_trace(go.Scatter(
            x=df_pivot.index,
            y=df_pivot[source] / 1000,
            name=label,
            mode="lines",
            stackgroup="one",
            line=dict(width=0, color=color),
            fillcolor=color,
            opacity=0.88,
            hovertemplate=f"<b>{label}</b>: %{{y:.1f}} GWh<extra></extra>",
        ))

    fig.update_layout(
        title=dict(text=title, font=dict(size=15, color=NAVY, family="Inter, sans-serif"), x=0),
        paper_bgcolor="white",
        plot_bgcolor="white",
        xaxis=dict(
            gridcolor=GRID, linecolor=GRID, tickfont=dict(size=10),
            tickformat="%d %b", hoverformat="%d %b %Y",
        ),
        yaxis=dict(gridcolor=GRID, linecolor=GRID, title="GWh", tickfont=dict(size=10)),
        margin=dict(l=48, r=16, t=56, b=72),
        legend=dict(
            orientation="h", yanchor="bottom", y=-0.30,
            xanchor="center", x=0.5, font=dict(size=10),
        ),
        hoverlabel=_HOVER,
        hovermode="x unified",
        annotations=_subtitle_ann(subtitle) + _footer(source_label, date_label),
        font=dict(family="Inter, sans-serif", color=NAVY),
    )
    return fig


# ── Gráfico 3: Barras renovable vs no renovable ───────────────────────────────

def chart_renewables_vs_nonrenewables(
    df: pd.DataFrame,
    title: str = "Renovable vs. no renovable",
    subtitle: str = "",
    date_label: str = "",
    source_label: str = "Fuente: ADME / UTE",
) -> go.Figure:
    """Barras apiladas mensuales: renovable vs. no renovable."""
    df = df.copy()
    df_grouped = (
        df[df["source_type"].isin(["renewable", "non_renewable"])]
        .groupby(["year_month", "source_type"])["value_mwh"]
        .sum()
        .unstack(fill_value=0)
        .reset_index()
    )

    fig = go.Figure()
    if "renewable" in df_grouped.columns:
        fig.add_trace(go.Bar(
            x=df_grouped["year_month"],
            y=df_grouped["renewable"] / 1000,
            name="Renovable",
            marker_color=GREEN,
            opacity=0.92,
            hovertemplate="<b>Renovable</b><br>%{x}<br>%{y:.0f} GWh<extra></extra>",
        ))
    if "non_renewable" in df_grouped.columns:
        fig.add_trace(go.Bar(
            x=df_grouped["year_month"],
            y=df_grouped["non_renewable"] / 1000,
            name="No renovable",
            marker_color="#E74C3C",
            opacity=0.88,
            hovertemplate="<b>No renovable</b><br>%{x}<br>%{y:.0f} GWh<extra></extra>",
        ))

    fig.update_layout(
        barmode="stack",
        title=dict(text=title, font=dict(size=15, color=NAVY, family="Inter, sans-serif"), x=0),
        paper_bgcolor="white",
        plot_bgcolor="white",
        xaxis=dict(gridcolor=GRID, linecolor=GRID, tickfont=dict(size=10)),
        yaxis=dict(gridcolor=GRID, linecolor=GRID, title="GWh", tickfont=dict(size=10)),
        margin=dict(l=48, r=16, t=56, b=72),
        legend=dict(
            orientation="h", yanchor="bottom", y=-0.30,
            xanchor="center", x=0.5, font=dict(size=10),
        ),
        hoverlabel=_HOVER,
        annotations=_subtitle_ann(subtitle) + _footer(source_label, date_label),
        font=dict(family="Inter, sans-serif", color=NAVY),
    )
    return fig


# ── Gráfico 4: Comparativa interanual ────────────────────────────────────────

def chart_yoy_comparison(
    df: pd.DataFrame,
    year_current: int,
    year_previous: int,
    source_filter: str | None = None,
    title: str = "Comparativa interanual",
    subtitle: str = "",
    date_label: str = "",
    source_label: str = "Fuente: ADME / UTE",
) -> go.Figure:
    """Barras agrupadas: año actual vs. año anterior por mes."""
    df = df.copy()
    if source_filter:
        df = df[df["source"] == source_filter]

    df["year"]  = df["year_month"].str[:4].astype(int)
    df["month"] = df["year_month"].str[5:7]

    df_agg = df.groupby(["year", "month"])["value_mwh"].sum().reset_index()
    months = sorted(df_agg["month"].unique())
    m_labels = {
        "01": "Ene", "02": "Feb", "03": "Mar", "04": "Abr",
        "05": "May", "06": "Jun", "07": "Jul", "08": "Ago",
        "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dic",
    }

    curr = df_agg[df_agg["year"] == year_current].set_index("month")["value_mwh"]
    prev = df_agg[df_agg["year"] == year_previous].set_index("month")["value_mwh"]
    x    = [m_labels.get(m, m) for m in months]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=x,
        y=[curr.get(m, 0) / 1000 for m in months],
        name=str(year_current),
        marker_color=NAVY,
        opacity=0.92,
        hovertemplate=f"<b>{year_current}</b><br>%{{x}}<br>%{{y:.0f}} GWh<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=x,
        y=[prev.get(m, 0) / 1000 for m in months],
        name=str(year_previous),
        marker_color=GREEN,
        opacity=0.65,
        hovertemplate=f"<b>{year_previous}</b><br>%{{x}}<br>%{{y:.0f}} GWh<extra></extra>",
    ))

    fig.update_layout(
        barmode="group",
        title=dict(text=title, font=dict(size=15, color=NAVY, family="Inter, sans-serif"), x=0),
        paper_bgcolor="white",
        plot_bgcolor="white",
        xaxis=dict(gridcolor=GRID, linecolor=GRID, tickfont=dict(size=10)),
        yaxis=dict(gridcolor=GRID, linecolor=GRID, title="GWh", tickfont=dict(size=10)),
        margin=dict(l=48, r=16, t=56, b=72),
        legend=dict(
            orientation="h", yanchor="bottom", y=-0.30,
            xanchor="center", x=0.5, font=dict(size=10),
        ),
        hoverlabel=_HOVER,
        annotations=_subtitle_ann(subtitle) + _footer(source_label, date_label),
        font=dict(family="Inter, sans-serif", color=NAVY),
    )
    return fig

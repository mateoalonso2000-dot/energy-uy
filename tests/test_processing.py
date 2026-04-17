"""
test_processing.py — Tests unitarios del módulo de procesamiento y limpieza.

Validan que las transformaciones básicas producen el output esperado
independientemente de la fuente de datos real.
"""

import pandas as pd
import pytest

from src.processing.cleaner import (
    clean_demand_daily,
    clean_generation_daily,
    clean_generation_hourly,
    clean_spot_price,
    _normalize_timestamp,
    _normalize_source,
)
from src.processing.transformer import (
    aggregate_hourly_to_daily,
    calculate_generation_share,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_hourly_df():
    """DataFrame simulado de generación horaria (formato ADME SCADA)."""
    return pd.DataFrame({
        "timestamp":   ["2024-01-15T10:00:00", "2024-01-15T11:00:00",
                        "2024-01-15T10:00:00", "2024-01-15T11:00:00"],
        "source":      ["wind", "wind", "solar", "solar"],
        "source_type": ["renewable", "renewable", "renewable", "renewable"],
        "plant_name":  ["Parque Valentines", "Parque Valentines", "Planta A", "Planta A"],
        "value_mw":    [120.5, 135.0, 45.2, 50.1],
        "data_source": ["adme_scada"] * 4,
    })


@pytest.fixture
def sample_daily_df():
    """DataFrame simulado de generación diaria (formato UTE Bajadas)."""
    return pd.DataFrame({
        "date":        ["2024-01-15", "2024-01-15", "2024-01-16", "2024-01-16"],
        "source":      ["wind", "solar", "wind", "thermal"],
        "source_type": ["renewable", "renewable", "renewable", "non_renewable"],
        "value_mwh":   [2880.0, 1200.0, 3100.0, 500.0],
        "data_source": ["ute_bajadas"] * 4,
    })


# ─── Tests de cleaner.py ──────────────────────────────────────────────────────

class TestNormalizeTimestamp:
    def test_iso_string_passthrough(self):
        s = pd.Series(["2024-01-15T10:00:00"])
        result = _normalize_timestamp(s, include_time=True)
        assert result.iloc[0] == "2024-01-15T10:00:00"

    def test_european_date_format(self):
        """Fecha en formato DD/MM/YYYY debe convertirse a YYYY-MM-DD."""
        s = pd.Series(["15/01/2024"])
        result = _normalize_timestamp(s, include_time=False)
        assert result.iloc[0] == "2024-01-15"

    def test_european_datetime_format(self):
        """Fecha y hora en formato DD/MM/YYYY HH:MM debe convertirse a ISO8601."""
        s = pd.Series(["15/01/2024 10:00"])
        result = _normalize_timestamp(s, include_time=True)
        assert result.iloc[0] == "2024-01-15T10:00:00"

    def test_invalid_date_becomes_nat(self):
        """Fechas inválidas deben retornar NaT (None como string)."""
        s = pd.Series(["not-a-date"])
        result = _normalize_timestamp(s, include_time=False)
        assert pd.isna(result.iloc[0])

    # ── Regresión: bug dayfirst=True ──────────────────────────────────────────
    # Con dayfirst=True, pandas interpreta "2025-01-13" como día=01, mes=13
    # → fecha inválida → NaT. Las fechas con día > 12 desaparecen silenciosamente.
    # Los tests siguientes garantizan que _normalize_timestamp NO transpone día/mes.

    def test_iso_date_day_greater_than_12_not_transposed(self):
        """
        Regresión dayfirst: '2025-01-15' no debe convertirse en NaT.
        Con dayfirst=True, pandas lo leía como mes=15 → inválido.
        """
        s = pd.Series(["2025-01-15"])
        result = _normalize_timestamp(s, include_time=False)
        assert result.iloc[0] == "2025-01-15", (
            "dayfirst bug: '2025-01-15' fue transpuesto a NaT. "
            "Verificar que _normalize_timestamp usa dayfirst=False."
        )

    def test_iso_datetime_day_greater_than_12_not_transposed(self):
        """
        Regresión dayfirst: '2025-01-15T10:00:00' no debe convertirse en NaT.
        """
        s = pd.Series(["2025-01-15T10:00:00"])
        result = _normalize_timestamp(s, include_time=True)
        assert result.iloc[0] == "2025-01-15T10:00:00", (
            "dayfirst bug: '2025-01-15T10:00:00' fue transpuesto a NaT."
        )

    def test_full_month_no_dates_dropped(self):
        """
        Regresión dayfirst: los 31 días de enero deben sobrevivir sin NaT.
        Con dayfirst=True, los días 13–31 se convertían en meses inválidos
        y eran descartados silenciosamente, dejando solo 12 fechas válidas.
        """
        dates = [f"2025-01-{d:02d}" for d in range(1, 32)]
        s = pd.Series(dates)
        result = _normalize_timestamp(s, include_time=False)
        n_nat = result.isna().sum()
        assert n_nat == 0, (
            f"dayfirst bug: {n_nat} fechas de enero se convirtieron en NaT. "
            "Verificar que _normalize_timestamp usa dayfirst=False."
        )
        assert len(result) == 31

    def test_day_and_month_not_swapped(self):
        """
        Regresión dayfirst: '2025-01-15' debe dar enero-15, no marzo-01 ni NaT.
        """
        s = pd.Series(["2025-01-15"])
        result = _normalize_timestamp(s, include_time=False)
        # Si hubiera transposición, sería "2025-15-01" → NaT, o "2025-03-01" (marzo)
        assert result.iloc[0] == "2025-01-15"


class TestNormalizeSource:
    def test_spanish_to_canonical(self):
        """'Eólica' → 'wind', 'Térmica' → 'thermal', etc."""
        sources = pd.Series(["Eólica", "Solar", "Térmica", "Biomasa", "Hidráulica"])
        result = _normalize_source(sources)
        expected = ["wind", "solar", "thermal", "biomass", "hydro"]
        assert list(result) == expected

    def test_case_insensitive(self):
        """La normalización debe ser insensible a mayúsculas."""
        sources = pd.Series(["EÓLICA", "solar", "Térmica"])
        result = _normalize_source(sources)
        assert result.iloc[0] == "wind"
        assert result.iloc[1] == "solar"
        assert result.iloc[2] == "thermal"

    def test_unknown_source_preserved(self):
        """Fuentes no mapeadas se preservan en minúsculas."""
        sources = pd.Series(["nuclear"])
        result = _normalize_source(sources)
        assert result.iloc[0] == "nuclear"


class TestCleanGenerationHourly:
    def test_output_columns(self, sample_hourly_df):
        """El DataFrame limpio debe tener exactamente las columnas esperadas."""
        result = clean_generation_hourly(sample_hourly_df)
        expected_cols = {"timestamp", "source", "source_type", "plant_name", "value_mw", "data_source"}
        assert set(result.columns) == expected_cols

    def test_no_negative_values(self):
        """Valores negativos de MW deben ser reemplazados por 0."""
        df = pd.DataFrame({
            "timestamp":   ["2024-01-15T10:00:00"],
            "source":      ["wind"],
            "source_type": ["renewable"],
            "plant_name":  [None],
            "value_mw":    [-50.0],
            "data_source": ["adme_scada"],
        })
        result = clean_generation_hourly(df)
        assert result["value_mw"].iloc[0] == 0.0

    def test_deduplication(self, sample_hourly_df):
        """Filas duplicadas deben eliminarse."""
        df_with_dupes = pd.concat([sample_hourly_df, sample_hourly_df], ignore_index=True)
        result = clean_generation_hourly(df_with_dupes)
        assert len(result) == len(sample_hourly_df)

    def test_nan_timestamps_dropped(self):
        """Filas con timestamp inválido deben eliminarse."""
        df = pd.DataFrame({
            "timestamp":   [None, "2024-01-15T10:00:00"],
            "source":      ["wind", "wind"],
            "source_type": ["renewable", "renewable"],
            "plant_name":  [None, None],
            "value_mw":    [100.0, 200.0],
            "data_source": ["adme_scada", "adme_scada"],
        })
        result = clean_generation_hourly(df)
        assert len(result) == 1


class TestCleanGenerationDaily:
    def test_output_columns(self, sample_daily_df):
        result = clean_generation_daily(sample_daily_df)
        expected_cols = {"date", "source", "source_type", "value_mwh", "data_source"}
        assert set(result.columns) == expected_cols

    def test_sorted_by_date(self, sample_daily_df):
        """El resultado debe estar ordenado por fecha."""
        result = clean_generation_daily(sample_daily_df)
        dates = result["date"].tolist()
        assert dates == sorted(dates)


# ─── Tests de transformer.py ──────────────────────────────────────────────────

class TestAggregateHourlyToDaily:
    def test_aggregation_sum(self, sample_hourly_df):
        """La suma de MW horarios para una fuente y día debe ser correcta."""
        result = aggregate_hourly_to_daily(sample_hourly_df)
        wind_row = result[result["source"] == "wind"]
        # 120.5 + 135.0 = 255.5
        assert abs(wind_row["value_mwh"].iloc[0] - 255.5) < 0.01

    def test_output_has_date_column(self, sample_hourly_df):
        result = aggregate_hourly_to_daily(sample_hourly_df)
        assert "date" in result.columns

    def test_reduces_rows(self, sample_hourly_df):
        """El número de filas debe reducirse respecto al input horario."""
        result = aggregate_hourly_to_daily(sample_hourly_df)
        assert len(result) < len(sample_hourly_df)


class TestCalculateGenerationShare:
    def test_shares_sum_to_100(self, sample_daily_df):
        """Las participaciones por día deben sumar 100%."""
        result = calculate_generation_share(sample_daily_df)
        for day in result["date"].unique():
            day_sum = result[result["date"] == day]["share_pct"].sum()
            assert abs(day_sum - 100.0) < 0.1

    def test_share_range(self, sample_daily_df):
        """Todos los shares deben estar entre 0 y 100."""
        result = calculate_generation_share(sample_daily_df)
        assert (result["share_pct"] >= 0).all()
        assert (result["share_pct"] <= 100).all()

"""
test_analysis.py — Tests del módulo de análisis e indicadores.
"""

import pandas as pd
import pytest

from src.analysis.indicators import (
    detect_anomalies,
    generation_mix,
    leading_source,
    renewable_share,
    demand_evolution,
)


@pytest.fixture
def sample_gen_df():
    return pd.DataFrame({
        "date":        ["2024-01-15"] * 4,
        "source":      ["wind", "solar", "thermal", "hydro"],
        "source_type": ["renewable", "renewable", "non_renewable", "renewable"],
        "value_mwh":   [3000.0, 1000.0, 500.0, 2000.0],
        "data_source": ["ute_bajadas"] * 4,
    })


@pytest.fixture
def sample_demand_df():
    return pd.DataFrame({
        "date":      ["2024-01-13", "2024-01-14", "2024-01-15"],
        "value_mwh": [8000.0, 8500.0, 7800.0],
        "data_source": ["ute_bajadas"] * 3,
    })


class TestGenerationMix:
    def test_shares_sum_to_100(self, sample_gen_df):
        result = generation_mix(sample_gen_df)
        assert abs(result["share_pct"].sum() - 100.0) < 0.1

    def test_sorted_descending(self, sample_gen_df):
        result = generation_mix(sample_gen_df)
        shares = result["share_pct"].tolist()
        assert shares == sorted(shares, reverse=True)

    def test_correct_leader(self, sample_gen_df):
        """La fuente líder debe ser wind (3000 MWh)."""
        result = generation_mix(sample_gen_df)
        assert result.iloc[0]["source"] == "wind"


class TestRenewableShare:
    def test_renewable_pct_correct(self, sample_gen_df):
        """Renovable: wind(3000) + solar(1000) + hydro(2000) = 6000 de 6500 = 92.3%"""
        result = renewable_share(sample_gen_df)
        assert abs(result["renewable_pct"] - (6000 / 6500 * 100)) < 0.1

    def test_keys_present(self, sample_gen_df):
        result = renewable_share(sample_gen_df)
        assert "renewable_mwh" in result
        assert "non_renewable_mwh" in result
        assert "total_mwh" in result
        assert "renewable_pct" in result

    def test_total_is_sum(self, sample_gen_df):
        result = renewable_share(sample_gen_df)
        assert abs(result["total_mwh"] - 6500.0) < 0.1


class TestLeadingSource:
    def test_returns_correct_source(self, sample_gen_df):
        mix = generation_mix(sample_gen_df)
        result = leading_source(mix)
        assert result["source"] == "wind"

    def test_has_required_keys(self, sample_gen_df):
        mix = generation_mix(sample_gen_df)
        result = leading_source(mix)
        assert "source" in result
        assert "share_pct" in result
        assert "total_mwh" in result


class TestDemandEvolution:
    def test_adds_ma_columns(self, sample_demand_df):
        result = demand_evolution(sample_demand_df)
        assert "ma_7d" in result.columns
        assert "ma_30d" in result.columns

    def test_delta_pct_first_row_is_nan(self, sample_demand_df):
        result = demand_evolution(sample_demand_df)
        assert pd.isna(result["delta_pct"].iloc[0])

    def test_delta_pct_second_row(self, sample_demand_df):
        """Delta del día 2: (8500 - 8000) / 8000 * 100 = 6.25%"""
        result = demand_evolution(sample_demand_df)
        assert abs(result["delta_pct"].iloc[1] - 6.25) < 0.01


class TestDetectAnomalies:
    def test_adds_anomaly_columns(self, sample_demand_df):
        result = detect_anomalies(sample_demand_df, "value_mwh")
        assert "z_score" in result.columns
        assert "is_anomaly" in result.columns

    def test_no_anomalies_in_normal_data(self, sample_demand_df):
        """Datos con poca variación no deben tener anomalías con z_threshold=2."""
        result = detect_anomalies(sample_demand_df, "value_mwh", z_threshold=2.0)
        assert result["is_anomaly"].sum() == 0

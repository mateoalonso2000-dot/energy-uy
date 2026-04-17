"""
test_storage.py — Tests del módulo de almacenamiento (upsert, queries).
"""

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from src.storage.database import get_engine, init_db
from src.storage.models import generation_daily
from src.storage.repository import (
    query_generation_daily,
    upsert_dataframe,
)


@pytest.fixture
def tmp_engine():
    """Crea un engine SQLite en un archivo temporal para cada test."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = Path(f.name)
    engine = get_engine(db_path)
    init_db(engine)
    yield engine
    engine.dispose()  # liberar conexión antes de borrar (necesario en Windows)
    db_path.unlink(missing_ok=True)


@pytest.fixture
def sample_gen_df():
    return pd.DataFrame({
        "date":        ["2024-01-15", "2024-01-15"],
        "source":      ["wind", "solar"],
        "source_type": ["renewable", "renewable"],
        "value_mwh":   [2880.0, 1200.0],
        "data_source": ["ute_bajadas", "ute_bajadas"],
    })


class TestUpsertDataframe:
    def test_insert_new_rows(self, tmp_engine, sample_gen_df):
        """Insertar filas nuevas debe retornar el conteo correcto."""
        inserted = upsert_dataframe(tmp_engine, generation_daily, sample_gen_df)
        assert inserted == 2

    def test_upsert_no_duplicate(self, tmp_engine, sample_gen_df):
        """Insertar el mismo DataFrame dos veces no debe duplicar filas."""
        upsert_dataframe(tmp_engine, generation_daily, sample_gen_df)
        inserted_second = upsert_dataframe(tmp_engine, generation_daily, sample_gen_df)
        assert inserted_second == 0

    def test_empty_dataframe_returns_zero(self, tmp_engine):
        """Un DataFrame vacío no debe insertar nada."""
        df_empty = pd.DataFrame(columns=["date", "source", "source_type", "value_mwh", "data_source"])
        inserted = upsert_dataframe(tmp_engine, generation_daily, df_empty)
        assert inserted == 0


class TestQueryGenerationDaily:
    def test_query_returns_inserted_data(self, tmp_engine, sample_gen_df):
        """Los datos insertados deben poder recuperarse con la query."""
        upsert_dataframe(tmp_engine, generation_daily, sample_gen_df)
        result = query_generation_daily(tmp_engine, "2024-01-01", "2024-01-31")
        assert len(result) == 2

    def test_query_date_filter(self, tmp_engine, sample_gen_df):
        """La query debe filtrar correctamente por rango de fechas."""
        upsert_dataframe(tmp_engine, generation_daily, sample_gen_df)
        result = query_generation_daily(tmp_engine, "2024-02-01", "2024-02-28")
        assert len(result) == 0

    def test_query_source_filter(self, tmp_engine, sample_gen_df):
        """El filtro por source debe retornar solo las filas solicitadas."""
        upsert_dataframe(tmp_engine, generation_daily, sample_gen_df)
        result = query_generation_daily(
            tmp_engine, "2024-01-01", "2024-01-31", sources=["wind"]
        )
        assert len(result) == 1
        assert result.iloc[0]["source"] == "wind"

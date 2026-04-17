"""
test_adme_scada.py — Tests unitarios del conector ADME SCADA GPF.

Todos los tests usan datos sintéticos o mocks. No realizan ninguna
conexión real a internet, por lo que son reproducibles sin acceso a ADME.
"""

import io
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.connectors.adme_scada import (
    COLUMN_RENAME,
    COLUMN_SOURCE_MAP,
    AdmeScadaConnector,
)
from src.connectors.base import ConnectorError


# ─── HTML de muestra (simula la respuesta de gpf.php) ────────────────────────

SAMPLE_HTML_WITH_ODS = """
<html>
<body>
  <p>Generación por Fuente</p>
  <a href="/cache/gpf_11111_22222_horario.ods">Descargar ODS</a>
</body>
</html>
"""

SAMPLE_HTML_WITHOUT_ODS = """
<html>
<body>
  <p>No hay datos para el período seleccionado.</p>
</body>
</html>
"""


# ─── ODS sintético ────────────────────────────────────────────────────────────

def _make_sample_ods() -> bytes:
    """
    Construye un ODS en memoria que replica la estructura real del GPF de ADME.

    Estructura:
        Fila 0: título SCADA (ignorado por skiprows=2)
        Fila 1: descripción  (ignorado por skiprows=2)
        Fila 2: encabezados
        Fila 3-4: dos registros horarios de ejemplo

    Nota: el engine 'odf' no soporta múltiples escrituras al mismo sheet con
    startrow, por lo que se construye una sola matriz con todas las filas.
    """
    columns = [
        "Fecha", "Salto Grande", "Bonete", "Baygorria", "Palmar",
        "Eólica", "Solar", "Térmica", "Biomasa",
        "Imp.Arg", "Imp.Br.Riv", "Imp.Br.Mel", "Demanda",
    ]
    title1 = ["Valores aproximados a partir de información del SCADA @ 2024-01-15"] + [""] * 12
    title2 = ["Datos generación e intercambios. Resumen"] + [""] * 12
    row1   = ["2024-01-15 00:00:00", 300.0, 120.0, 80.0, 100.0, 450.0, 90.0, 50.0, 30.0, 0.0, 0.0, 0.0, 1220.0]
    row2   = ["2024-01-15 01:00:00", 290.0, 115.0, 78.0, 98.0, 420.0, 0.0, 55.0, 30.0, 10.0, 0.0, 0.0, 1096.0]

    all_rows = pd.DataFrame([title1, title2, columns, row1, row2])

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="odf") as writer:
        all_rows.to_excel(writer, sheet_name="GPF", index=False, header=False)
    buf.seek(0)
    return buf.read()


# ─── Fixture del conector ────────────────────────────────────────────────────

@pytest.fixture
def connector():
    return AdmeScadaConnector()


# ─── Tests de _extract_ods_url ────────────────────────────────────────────────

class TestExtractOdsUrl:
    def test_extracts_url_from_valid_html(self, connector):
        """Debe extraer la URL del ODS del HTML de muestra."""
        url = connector._extract_ods_url(SAMPLE_HTML_WITH_ODS)
        assert url == "https://pronos.adme.com.uy/cache/gpf_11111_22222_horario.ods"

    def test_builds_absolute_url(self, connector):
        """La URL retornada debe ser absoluta (comenzar con https://)."""
        url = connector._extract_ods_url(SAMPLE_HTML_WITH_ODS)
        assert url.startswith("https://")

    def test_raises_if_no_ods_link(self, connector):
        """Debe lanzar ConnectorError si no hay ningún link .ods en el HTML."""
        with pytest.raises(ConnectorError) as exc_info:
            connector._extract_ods_url(SAMPLE_HTML_WITHOUT_ODS)
        assert "adme_scada" in str(exc_info.value)
        assert ".ods" in str(exc_info.value).lower() or "link" in str(exc_info.value).lower()

    def test_uses_first_link_when_multiple(self, connector):
        """Si hay más de un link .ods, debe usar el primero."""
        html = """
        <a href="/cache/gpf_first.ods">primero</a>
        <a href="/cache/gpf_second.ods">segundo</a>
        """
        url = connector._extract_ods_url(html)
        assert "first" in url


# ─── Tests de _parse_gpf_sheet ───────────────────────────────────────────────

class TestParseGpfSheet:
    def test_output_has_expected_columns(self, connector):
        """El DataFrame ancho debe tener timestamp y las columnas renombradas."""
        ods = _make_sample_ods()
        df  = connector._parse_gpf_sheet(ods)

        expected_internal_names = set(COLUMN_RENAME.values())
        actual_cols = set(df.columns)
        assert "timestamp" in actual_cols
        # Al menos la mayoría de las columnas internas deben estar presentes
        assert len(expected_internal_names & actual_cols) >= 10

    def test_timestamp_is_datetime(self, connector):
        """La columna timestamp debe ser de tipo datetime64."""
        ods = _make_sample_ods()
        df  = connector._parse_gpf_sheet(ods)
        assert pd.api.types.is_datetime64_any_dtype(df["timestamp"])

    def test_value_columns_are_float(self, connector):
        """Las columnas de valores deben ser numéricas (float)."""
        ods = _make_sample_ods()
        df  = connector._parse_gpf_sheet(ods)
        value_cols = [c for c in df.columns if c != "timestamp"]
        for col in value_cols:
            assert pd.api.types.is_numeric_dtype(df[col]), (
                f"La columna '{col}' no es numérica: {df[col].dtype}"
            )

    def test_correct_row_count(self, connector):
        """El ODS sintético tiene 2 filas de datos; deben retornarse las 2."""
        ods = _make_sample_ods()
        df  = connector._parse_gpf_sheet(ods)
        assert len(df) == 2

    def test_raises_on_empty_sheet(self, connector):
        """Debe lanzar ConnectorError si la hoja GPF está vacía."""
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="odf") as writer:
            pd.DataFrame().to_excel(writer, sheet_name="GPF", index=False)
        buf.seek(0)

        with pytest.raises(ConnectorError):
            connector._parse_gpf_sheet(buf.read())


# ─── Tests de _to_long_format ────────────────────────────────────────────────

class TestToLongFormat:
    @pytest.fixture
    def wide_df(self, connector):
        ods = _make_sample_ods()
        return connector._parse_gpf_sheet(ods)

    def test_output_columns(self, connector, wide_df):
        """El DataFrame largo debe tener exactamente las columnas del pipeline."""
        df = connector._to_long_format(wide_df)
        required = {"timestamp", "source", "source_type", "plant_name", "value_mw"}
        assert required.issubset(set(df.columns))

    def test_timestamp_is_iso8601_string(self, connector, wide_df):
        """El timestamp debe estar en formato ISO8601 string para el pipeline."""
        df = connector._to_long_format(wide_df)
        sample = df["timestamp"].iloc[0]
        assert isinstance(sample, str)
        # Debe ser parseable como datetime
        pd.to_datetime(sample)

    def test_no_negative_generation_values(self, connector, wide_df):
        """
        Las columnas de generación no deben tener valores negativos.
        (Importaciones pueden ser negativas en algunos sistemas, pero en ADME
        vienen como positivos con dirección implícita en el nombre de columna.)
        """
        df = connector._to_long_format(wide_df)
        gen_sources = {"hydro", "wind", "solar", "thermal", "biomass"}
        df_gen = df[df["source"].isin(gen_sources)]
        assert (df_gen["value_mw"] >= 0).all(), (
            "Se encontraron valores negativos en columnas de generación."
        )

    def test_all_sources_present(self, connector, wide_df):
        """Deben aparecer todas las fuentes definidas en COLUMN_SOURCE_MAP."""
        df = connector._to_long_format(wide_df)
        expected_sources = {v[0] for v in COLUMN_SOURCE_MAP.values()}
        actual_sources   = set(df["source"].unique())
        assert expected_sources == actual_sources

    def test_hydro_has_plant_name(self, connector, wide_df):
        """Las centrales hidro deben tener plant_name no nulo."""
        df = connector._to_long_format(wide_df)
        hydro_rows = df[df["source"] == "hydro"]
        assert hydro_rows["plant_name"].notna().all()

    def test_wind_has_no_plant_name(self, connector, wide_df):
        """La eólica agregada no tiene planta individual → plant_name debe ser None."""
        df = connector._to_long_format(wide_df)
        wind_rows = df[df["source"] == "wind"]
        assert wind_rows["plant_name"].isna().all()

    def test_row_count_is_sources_times_timestamps(self, connector, wide_df):
        """Filas = fuentes × timestamps."""
        df          = connector._to_long_format(wide_df)
        n_sources   = len(COLUMN_SOURCE_MAP)
        n_timestamps = len(wide_df)
        assert len(df) == n_sources * n_timestamps


# ─── Tests de validate ────────────────────────────────────────────────────────

class TestValidate:
    def test_valid_dataframe_passes(self, connector):
        df = pd.DataFrame({
            "timestamp":   ["2024-01-15T00:00:00"],
            "source":      ["wind"],
            "source_type": ["renewable"],
            "plant_name":  [None],
            "value_mw":    [100.0],
            "data_source": ["adme_scada"],
        })
        assert connector.validate(df) is True

    def test_missing_column_fails(self, connector):
        df = pd.DataFrame({
            "timestamp": ["2024-01-15T00:00:00"],
            "source":    ["wind"],
        })
        assert connector.validate(df) is False

    def test_all_nan_values_fails(self, connector):
        df = pd.DataFrame({
            "timestamp":   ["2024-01-15T00:00:00"],
            "source":      ["wind"],
            "source_type": ["renewable"],
            "value_mw":    [float("nan")],
            "data_source": ["adme_scada"],
        })
        assert connector.validate(df) is False

    def test_empty_dataframe_fails(self, connector):
        df = pd.DataFrame(
            columns=["timestamp", "source", "source_type", "value_mw", "data_source"]
        )
        assert connector.validate(df) is False


# ─── Test de integración (mock de red) ───────────────────────────────────────

class TestFetchIntegration:
    def test_fetch_returns_correct_shape(self, connector):
        """
        Test de integración con red mockeada.
        Verifica que fetch() retorna el DataFrame con la forma esperada
        usando respuestas HTTP simuladas.
        """
        sample_ods = _make_sample_ods()

        mock_html_response = MagicMock()
        mock_html_response.text = SAMPLE_HTML_WITH_ODS
        mock_html_response.raise_for_status = MagicMock()

        mock_ods_response = MagicMock()
        mock_ods_response.content = sample_ods
        mock_ods_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = [mock_html_response, mock_ods_response]

        with patch("src.connectors.adme_scada.httpx.Client", return_value=mock_client):
            df = connector.fetch(date(2024, 1, 15), date(2024, 1, 15))

        # Verificar estructura
        assert not df.empty
        assert "timestamp" in df.columns
        assert "source" in df.columns
        assert "value_mw" in df.columns
        assert "data_source" in df.columns
        assert (df["data_source"] == "adme_scada").all()

    def test_fetch_raises_on_http_error(self, connector):
        """fetch() debe lanzar ConnectorError si el GET a gpf.php falla."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = Exception("connection refused")

        with patch("src.connectors.adme_scada.httpx.Client", return_value=mock_client):
            with pytest.raises((ConnectorError, Exception)):
                connector.fetch(date(2024, 1, 15), date(2024, 1, 15))

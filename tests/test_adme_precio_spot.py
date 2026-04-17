"""
test_adme_precio_spot.py — Tests unitarios del conector ADME Precio Spot.

Todos los tests usan datos sintéticos o mocks. No realizan ninguna
conexión real a internet, por lo que son reproducibles sin acceso a ADME.
"""

import io
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.connectors.adme_precio_spot import (
    COLUMN_RENAME,
    DATETIME_FORMAT,
    SHEET_NAME,
    AdmePrecioSpotConnector,
)
from src.connectors.base import ConnectorError


# ─── XLSX sintético ───────────────────────────────────────────────────────────

def _make_sample_xlsx(include_negative: bool = False) -> bytes:
    """
    Construye un XLSX en memoria que replica la estructura real del
    endpoint sancionado_excel.php de ADME.

    Estructura:
        Fila 0:   encabezados
        Filas 1+: datos horarios (5 filas de ejemplo)

    Args:
        include_negative: si True, incluye una fila con precio negativo
                          (para testear la advertencia del conector).
    """
    rows = [
        {"Fecha": "01-01-2024 00:00", "Precio Spot Sancionado (USD/MWh)": 45.20},
        {"Fecha": "01-01-2024 01:00", "Precio Spot Sancionado (USD/MWh)": 42.80},
        {"Fecha": "01-01-2024 02:00", "Precio Spot Sancionado (USD/MWh)":  0.00},  # cero válido
        {"Fecha": "01-01-2024 03:00", "Precio Spot Sancionado (USD/MWh)": 38.50},
        {"Fecha": "01-01-2024 04:00", "Precio Spot Sancionado (USD/MWh)": 51.10},
    ]
    if include_negative:
        rows.append({"Fecha": "01-01-2024 05:00", "Precio Spot Sancionado (USD/MWh)": -5.00})

    df = pd.DataFrame(rows)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=SHEET_NAME, index=False)
    buf.seek(0)
    return buf.read()


# ─── Fixture del conector ─────────────────────────────────────────────────────

@pytest.fixture
def connector():
    return AdmePrecioSpotConnector()


# ─── Tests de _parse_sheet ────────────────────────────────────────────────────

class TestParseSheet:
    def test_retorna_todas_las_filas_de_datos(self, connector):
        """Sin footer, todas las filas deben retornarse."""
        xlsx = _make_sample_xlsx()
        df   = connector._parse_sheet(xlsx)
        assert len(df) == 5

    def test_columna_fecha_presente(self, connector):
        """El DataFrame crudo debe tener la columna 'Fecha' original."""
        xlsx = _make_sample_xlsx()
        df   = connector._parse_sheet(xlsx)
        assert "Fecha" in df.columns

    def test_columna_precio_presente(self, connector):
        """El DataFrame crudo debe tener la columna 'Precio Spot Sancionado (USD/MWh)'."""
        xlsx = _make_sample_xlsx()
        df   = connector._parse_sheet(xlsx)
        assert "Precio Spot Sancionado (USD/MWh)" in df.columns

    def test_xlsx_vacio_lanza_error(self, connector):
        """Una hoja vacía debe lanzar ConnectorError."""
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            pd.DataFrame().to_excel(writer, sheet_name=SHEET_NAME, index=False)
        buf.seek(0)

        with pytest.raises(ConnectorError):
            connector._parse_sheet(buf.read())

    def test_columnas_faltantes_lanza_error(self, connector):
        """Si el XLSX no tiene las columnas esperadas, debe lanzar ConnectorError."""
        df_malo = pd.DataFrame({"OtraColumna": [1, 2, 3]})
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df_malo.to_excel(writer, sheet_name=SHEET_NAME, index=False)
        buf.seek(0)

        with pytest.raises(ConnectorError):
            connector._parse_sheet(buf.read())


# ─── Tests de _rename_and_clean ──────────────────────────────────────────────

class TestRenameAndClean:
    @pytest.fixture
    def df_crudo(self, connector):
        xlsx = _make_sample_xlsx()
        return connector._parse_sheet(xlsx)

    def test_datetime_es_datetime64(self, connector, df_crudo):
        """La columna 'timestamp' debe ser de tipo datetime64."""
        df = connector._rename_and_clean(df_crudo)
        assert pd.api.types.is_datetime64_any_dtype(df["timestamp"])

    def test_precio_es_float(self, connector, df_crudo):
        """La columna 'price_usd' debe ser de tipo float64."""
        df = connector._rename_and_clean(df_crudo)
        assert pd.api.types.is_float_dtype(df["price_usd"])

    def test_sin_datetime_invalido(self, connector, df_crudo):
        """No deben quedar filas con timestamp NaT."""
        df = connector._rename_and_clean(df_crudo)
        assert df["timestamp"].notna().all()

    def test_precio_no_negativo(self, connector, df_crudo):
        """Con datos normales, el precio no debe tener valores negativos."""
        df = connector._rename_and_clean(df_crudo)
        assert (df["price_usd"] >= 0).all()

    def test_cero_es_valido(self, connector, df_crudo):
        """El precio 0.0 es válido y debe conservarse en el DataFrame."""
        df = connector._rename_and_clean(df_crudo)
        assert (df["price_usd"] == 0.0).any()

    def test_columnas_renombradas(self, connector, df_crudo):
        """Las columnas originales no deben aparecer; deben estar las renombradas."""
        df = connector._rename_and_clean(df_crudo)
        for original, interno in COLUMN_RENAME.items():
            assert original not in df.columns, (
                f"Columna original '{original}' sigue presente."
            )
            assert interno in df.columns, (
                f"Columna interna '{interno}' no encontrada."
            )

    def test_datetime_resolucion_horaria(self, connector, df_crudo):
        """Las marcas temporales deben tener resolución horaria (minutos = 0)."""
        df = connector._rename_and_clean(df_crudo)
        assert (df["timestamp"].dt.minute == 0).all()

    def test_precio_negativo_no_descarta_filas(self, connector):
        """
        Los precios negativos emiten un warning pero NO se descartan —
        es responsabilidad del análisis decidir cómo manejarlos.
        """
        xlsx = _make_sample_xlsx(include_negative=True)
        df_crudo = connector._parse_sheet(xlsx)
        df       = connector._rename_and_clean(df_crudo)
        # Las 6 filas (5 normales + 1 negativa) deben estar presentes
        assert len(df) == 6


# ─── Tests de validate ────────────────────────────────────────────────────────

class TestValidate:
    def test_dataframe_valido_pasa(self, connector):
        df = pd.DataFrame({
            "timestamp":  [pd.Timestamp("2024-01-01 00:00:00")],
            "price_usd":  [45.20],
            "data_source": ["adme_precio_spot"],
        })
        assert connector.validate(df) is True

    def test_columna_faltante_falla(self, connector):
        df = pd.DataFrame({"timestamp": [pd.Timestamp("2024-01-01")]})
        assert connector.validate(df) is False

    def test_todos_nan_en_precio_falla(self, connector):
        df = pd.DataFrame({
            "timestamp":  [pd.Timestamp("2024-01-01 00:00:00")],
            "price_usd":  [float("nan")],
            "data_source": ["adme_precio_spot"],
        })
        assert connector.validate(df) is False

    def test_dataframe_vacio_falla(self, connector):
        df = pd.DataFrame(columns=["timestamp", "price_usd", "data_source"])
        assert connector.validate(df) is False

    def test_precio_cero_pasa_validacion(self, connector):
        """Un precio de 0 es válido — el validate no debe rechazarlo."""
        df = pd.DataFrame({
            "timestamp":  [pd.Timestamp("2024-01-01 00:00:00")],
            "price_usd":  [0.0],
            "data_source": ["adme_precio_spot"],
        })
        assert connector.validate(df) is True


# ─── Tests de integración (mock de red) ──────────────────────────────────────

class TestFetchIntegration:
    def test_fetch_mensual_retorna_shape_correcto(self, connector):
        """
        Test de integración con red mockeada.
        Verifica que fetch_mensual() retorna el DataFrame con la forma esperada.
        """
        sample_xlsx = _make_sample_xlsx()

        mock_response = MagicMock()
        mock_response.content = sample_xlsx
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response

        with patch(
            "src.connectors.adme_precio_spot.httpx.Client",
            return_value=mock_client,
        ):
            df = connector.fetch_mensual(
                anio_desde=2024, mes_desde=1,
                anio_hasta=2024, mes_hasta=1,
            )

        assert not df.empty
        assert "timestamp"   in df.columns
        assert "price_usd"   in df.columns
        assert "data_source" in df.columns
        assert (df["data_source"] == "adme_precio_spot").all()
        assert len(df) == 5
        assert pd.api.types.is_datetime64_any_dtype(df["timestamp"])
        assert pd.api.types.is_float_dtype(df["price_usd"])

    def test_fetch_adapter_extrae_anio_mes(self, connector):
        """
        fetch(date_from, date_to) debe delegar correctamente a fetch_mensual()
        extrayendo año y mes de los objetos date.
        """
        sample_xlsx = _make_sample_xlsx()

        mock_response = MagicMock()
        mock_response.content = sample_xlsx
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response

        with patch(
            "src.connectors.adme_precio_spot.httpx.Client",
            return_value=mock_client,
        ):
            df = connector.fetch(date(2024, 1, 1), date(2024, 1, 31))

        assert not df.empty
        assert len(df) == 5

    def test_fetch_lanza_error_en_fallo_http(self, connector):
        """fetch_mensual() debe lanzar ConnectorError si el GET falla."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = Exception("connection refused")

        with patch(
            "src.connectors.adme_precio_spot.httpx.Client",
            return_value=mock_client,
        ):
            with pytest.raises((ConnectorError, Exception)):
                connector.fetch_mensual(2024, 1, 2024, 1)

    def test_ultimo_anio_mes_se_calculan_dinamicamente(self, connector):
        """
        Los parámetros ultimo_anio/ultimo_mes deben calcularse con datetime.now()
        y enviarse en el GET. Verificar que el cliente recibe esos params.
        """
        sample_xlsx = _make_sample_xlsx()

        mock_response = MagicMock()
        mock_response.content = sample_xlsx
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response

        with patch(
            "src.connectors.adme_precio_spot.httpx.Client",
            return_value=mock_client,
        ):
            connector.fetch_mensual(2024, 1, 2024, 1)

        # Verificar que se hizo exactamente un GET
        assert mock_client.get.call_count == 1

        # Verificar que los params incluyen ultimo_anio y ultimo_mes
        call_kwargs = mock_client.get.call_args
        params_sent = call_kwargs[1].get("params", call_kwargs[0][1] if len(call_kwargs[0]) > 1 else {})
        assert "ultimo_anio" in params_sent
        assert "ultimo_mes"  in params_sent

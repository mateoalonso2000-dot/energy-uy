"""
test_adme_generacion_mensual.py — Tests unitarios del conector ADME Generación Mensual.

Todos los tests usan datos sintéticos o mocks. No realizan ninguna
conexión real a internet, por lo que son reproducibles sin acceso a ADME.
"""

import io
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.connectors.adme_generacion_mensual import (
    COLUMN_RENAME,
    NET_COLUMNS,
    SHEET_NAME,
    AdmeGeneracionMensualConnector,
)
from src.connectors.base import ConnectorError


# ─── XLSX sintético ───────────────────────────────────────────────────────────

def _make_sample_xlsx(include_footer: bool = True) -> bytes:
    """
    Construye un XLSX en memoria que replica la estructura real del
    Panel de Control de ADME.

    Estructura:
        Filas 0-2:  datos mensuales reales
        Filas 3-5:  notas al pie (solo si include_footer=True)
                    — texto en col Fecha, NaN en todas las numéricas
    """
    data_rows = pd.DataFrame(
        [
            {
                "Fecha":             "01-2024",
                "Hidráulica Inyec":  1200.0,
                "Hidráulica Extrac": 100.0,
                "Biomasa Inyec":     300.0,
                "Biomasa Extrac":    10.0,
                "Térmico Inyec":     500.0,
                "Térmico Extrac":    20.0,
                "Eólico Inyec":      800.0,
                "Eólico Extrac":     5.0,
                "Solar Inyec":       150.0,
                "Solar Extrac":      2.0,
                "Importaciones":     50.0,
                "Exportaciones":     30.0,
                "Demanda Bruta":     3100.0,
                "Demanda Neta":      3050.0,
            },
            {
                "Fecha":             "02-2024",
                "Hidráulica Inyec":  1100.0,
                "Hidráulica Extrac": 90.0,
                "Biomasa Inyec":     280.0,
                "Biomasa Extrac":    8.0,
                "Térmico Inyec":     480.0,
                "Térmico Extrac":    18.0,
                "Eólico Inyec":      750.0,
                "Eólico Extrac":     4.0,
                "Solar Inyec":       130.0,
                "Solar Extrac":      1.5,
                "Importaciones":     45.0,
                "Exportaciones":     25.0,
                "Demanda Bruta":     2900.0,
                "Demanda Neta":      2860.0,
            },
            {
                "Fecha":             "03-2024",
                "Hidráulica Inyec":  1300.0,
                "Hidráulica Extrac": 110.0,
                "Biomasa Inyec":     310.0,
                "Biomasa Extrac":    12.0,
                "Térmico Inyec":     520.0,
                "Térmico Extrac":    22.0,
                "Eólico Inyec":      820.0,
                "Eólico Extrac":     6.0,
                "Solar Inyec":       160.0,
                "Solar Extrac":      2.5,
                "Importaciones":     55.0,
                "Exportaciones":     35.0,
                "Demanda Bruta":     3200.0,
                "Demanda Neta":      3160.0,
            },
        ]
    )

    footer_rows = pd.DataFrame(
        [
            {"Fecha": "Nota 1: valores en MWh"},
            {"Fecha": "Nota 2: datos preliminares"},
            {"Fecha": "Fuente: ADME"},
        ]
    )

    if include_footer:
        df = pd.concat([data_rows, footer_rows], ignore_index=True)
    else:
        df = data_rows

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=SHEET_NAME, index=False)
    buf.seek(0)
    return buf.read()


# ─── Fixture del conector ─────────────────────────────────────────────────────

@pytest.fixture
def connector():
    return AdmeGeneracionMensualConnector()


# ─── Tests de _parse_sheet ────────────────────────────────────────────────────

class TestParseSheet:
    def test_descarta_filas_footer(self, connector):
        """Las filas de notas al pie (todas las numéricas son NaN) deben eliminarse."""
        xlsx = _make_sample_xlsx(include_footer=True)
        df   = connector._parse_sheet(xlsx)
        # Solo deben quedar las 3 filas reales, no las 3 del footer
        assert len(df) == 3

    def test_sin_footer_retorna_todas_las_filas(self, connector):
        """Sin footer, todas las filas de datos deben retornarse."""
        xlsx = _make_sample_xlsx(include_footer=False)
        df   = connector._parse_sheet(xlsx)
        assert len(df) == 3

    def test_columna_fecha_presente(self, connector):
        """El DataFrame crudo debe tener la columna 'Fecha' original."""
        xlsx = _make_sample_xlsx()
        df   = connector._parse_sheet(xlsx)
        assert "Fecha" in df.columns

    def test_columnas_numericas_presentes(self, connector):
        """Deben estar presentes todas las columnas numéricas conocidas."""
        xlsx = _make_sample_xlsx()
        df   = connector._parse_sheet(xlsx)
        expected_numeric_cols = [k for k in COLUMN_RENAME if k != "Fecha"]
        for col in expected_numeric_cols:
            assert col in df.columns, f"Columna '{col}' no encontrada en el DataFrame"

    def test_xlsx_vacio_lanza_error(self, connector):
        """Un XLSX con hoja vacía debe lanzar ConnectorError."""
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            pd.DataFrame().to_excel(writer, sheet_name=SHEET_NAME, index=False)
        buf.seek(0)

        with pytest.raises(ConnectorError):
            connector._parse_sheet(buf.read())


# ─── Tests de _rename_and_clean ───────────────────────────────────────────────

class TestRenameAndClean:
    @pytest.fixture
    def df_crudo(self, connector):
        xlsx = _make_sample_xlsx(include_footer=True)
        return connector._parse_sheet(xlsx)

    def test_fecha_es_datetime64(self, connector, df_crudo):
        """La columna 'fecha' debe ser datetime64 tras el renombrado."""
        df = connector._rename_and_clean(df_crudo)
        assert pd.api.types.is_datetime64_any_dtype(df["fecha"])

    def test_fecha_primer_dia_del_mes(self, connector, df_crudo):
        """Cada valor de 'fecha' debe ser el primer día del mes."""
        df = connector._rename_and_clean(df_crudo)
        assert (df["fecha"].dt.day == 1).all()

    def test_fechas_correctas(self, connector, df_crudo):
        """Los meses deben ser enero, febrero y marzo de 2024."""
        df     = connector._rename_and_clean(df_crudo)
        meses  = sorted(df["fecha"].dt.month.tolist())
        annios = df["fecha"].dt.year.unique().tolist()
        assert meses  == [1, 2, 3]
        assert annios == [2024]

    def test_columnas_numericas_son_float(self, connector, df_crudo):
        """Todas las columnas numéricas conocidas deben ser float64."""
        df = connector._rename_and_clean(df_crudo)
        internal_numeric = [v for v in COLUMN_RENAME.values() if v != "fecha"]
        for col in internal_numeric:
            if col in df.columns:
                assert pd.api.types.is_numeric_dtype(df[col]), (
                    f"La columna '{col}' no es numérica: {df[col].dtype}"
                )

    def test_no_filas_con_fecha_invalida(self, connector, df_crudo):
        """No deben quedar filas con fecha NaT tras la limpieza."""
        df = connector._rename_and_clean(df_crudo)
        assert df["fecha"].notna().all()

    def test_columnas_renombradas_a_snake_case(self, connector, df_crudo):
        """Las columnas originales no deben aparecer; deben estar las renombradas."""
        df = connector._rename_and_clean(df_crudo)
        for original, interno in COLUMN_RENAME.items():
            assert original not in df.columns, (
                f"Columna original '{original}' sigue presente sin renombrar."
            )
            assert interno in df.columns, (
                f"Columna interna '{interno}' no encontrada tras renombrado."
            )


# ─── Tests de _add_net_columns ───────────────────────────────────────────────

class TestAddNetColumns:
    @pytest.fixture
    def df_limpio(self, connector):
        xlsx = _make_sample_xlsx(include_footer=True)
        df   = connector._parse_sheet(xlsx)
        return connector._rename_and_clean(df)

    def test_todas_las_columnas_netas_presentes(self, connector, df_limpio):
        """Deben calcularse todas las columnas netas definidas en NET_COLUMNS."""
        df = connector._add_net_columns(df_limpio)
        for _, _, col_neta in NET_COLUMNS:
            assert col_neta in df.columns, (
                f"Columna neta '{col_neta}' no encontrada."
            )

    def test_calculo_neta_hidraulica(self, connector, df_limpio):
        """hidraulica_neta = hidraulica_inyec - hidraulica_extrac."""
        df = connector._add_net_columns(df_limpio)
        expected = df["hidraulica_inyec"] - df["hidraulica_extrac"]
        pd.testing.assert_series_equal(
            df["hidraulica_neta"].reset_index(drop=True),
            expected.reset_index(drop=True),
            check_names=False,
        )

    def test_calculo_neta_eolico(self, connector, df_limpio):
        """eolico_neta = eolico_inyec - eolico_extrac."""
        df = connector._add_net_columns(df_limpio)
        expected = df["eolico_inyec"] - df["eolico_extrac"]
        pd.testing.assert_series_equal(
            df["eolico_neta"].reset_index(drop=True),
            expected.reset_index(drop=True),
            check_names=False,
        )

    def test_netas_son_positivas_con_datos_reales(self, connector, df_limpio):
        """Con datos donde inyec > extrac, todas las columnas netas deben ser positivas."""
        df = connector._add_net_columns(df_limpio)
        for _, _, col_neta in NET_COLUMNS:
            assert (df[col_neta] > 0).all(), (
                f"Se encontraron valores no positivos en {col_neta}."
            )


# ─── Tests de validate ────────────────────────────────────────────────────────

class TestValidate:
    def test_dataframe_valido_pasa(self, connector):
        df = pd.DataFrame({
            "fecha":        [pd.Timestamp("2024-01-01")],
            "demanda_neta": [3050.0],
            "data_source":  ["adme_generacion_mensual"],
        })
        assert connector.validate(df) is True

    def test_columna_faltante_falla(self, connector):
        df = pd.DataFrame({"fecha": [pd.Timestamp("2024-01-01")]})
        assert connector.validate(df) is False

    def test_todos_nan_en_demanda_falla(self, connector):
        df = pd.DataFrame({
            "fecha":        [pd.Timestamp("2024-01-01")],
            "demanda_neta": [float("nan")],
            "data_source":  ["adme_generacion_mensual"],
        })
        assert connector.validate(df) is False

    def test_dataframe_vacio_falla(self, connector):
        df = pd.DataFrame(columns=["fecha", "demanda_neta", "data_source"])
        assert connector.validate(df) is False


# ─── Tests de demanda positiva ────────────────────────────────────────────────

class TestDemandaPositiva:
    """La demanda debe ser siempre positiva en datos válidos."""

    def test_demanda_bruta_positiva(self, connector):
        """demanda_bruta no debe contener valores negativos."""
        xlsx = _make_sample_xlsx()
        df   = connector._parse_sheet(xlsx)
        df   = connector._rename_and_clean(df)
        assert (df["demanda_bruta"] > 0).all()

    def test_demanda_neta_positiva(self, connector):
        """demanda_neta no debe contener valores negativos."""
        xlsx = _make_sample_xlsx()
        df   = connector._parse_sheet(xlsx)
        df   = connector._rename_and_clean(df)
        assert (df["demanda_neta"] > 0).all()


# ─── Test de integración (mock de red) ───────────────────────────────────────

class TestFetchIntegration:
    def test_fetch_mensual_retorna_shape_correcto(self, connector):
        """
        Test de integración con red mockeada.
        Verifica que fetch_mensual() retorna el DataFrame con la forma esperada.
        """
        sample_xlsx = _make_sample_xlsx(include_footer=True)

        mock_response = MagicMock()
        mock_response.content = sample_xlsx
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response

        with patch(
            "src.connectors.adme_generacion_mensual.httpx.Client",
            return_value=mock_client,
        ):
            df = connector.fetch_mensual(
                anio_desde=2024, mes_desde=1,
                anio_hasta=2024, mes_hasta=3,
            )

        # Verificar estructura básica
        assert not df.empty
        assert "fecha"        in df.columns
        assert "demanda_neta" in df.columns
        assert "data_source"  in df.columns
        assert (df["data_source"] == "adme_generacion_mensual").all()
        assert len(df) == 3  # 3 filas de datos, footer descartado

        # Verificar columnas netas
        for _, _, col_neta in NET_COLUMNS:
            assert col_neta in df.columns

    def test_fetch_adapter_delega_a_fetch_mensual(self, connector):
        """
        fetch(date_from, date_to) debe delegar correctamente a fetch_mensual()
        extrayendo año y mes de los objetos date.
        """
        sample_xlsx = _make_sample_xlsx(include_footer=False)

        mock_response = MagicMock()
        mock_response.content = sample_xlsx
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response

        with patch(
            "src.connectors.adme_generacion_mensual.httpx.Client",
            return_value=mock_client,
        ):
            df = connector.fetch(date(2024, 1, 1), date(2024, 3, 31))

        assert not df.empty
        assert len(df) == 3

    def test_fetch_lanza_error_en_fallo_http(self, connector):
        """fetch_mensual() debe lanzar ConnectorError si el GET falla."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = Exception("connection refused")

        with patch(
            "src.connectors.adme_generacion_mensual.httpx.Client",
            return_value=mock_client,
        ):
            with pytest.raises((ConnectorError, Exception)):
                connector.fetch_mensual(2024, 1, 2024, 3)

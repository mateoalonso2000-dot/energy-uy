"""
ute_bajadas.py — Conector para el portal de descarga SGE Público de UTE.

Fuente: https://apps.ute.com.uy/SgePublico/Bajadas.aspx
Formato: XLSX o CSV descargado vía formulario ASPX (WebForms .NET).
Granularidad: diaria (a confirmar).

SUPUESTO TÉCNICO:
    La página ASPX usa __VIEWSTATE. La estrategia es:
    1. GET inicial para capturar __VIEWSTATE y __EVENTVALIDATION.
    2. POST con esos tokens + nombre del dataset solicitado.
    3. El servidor responde con el archivo XLSX/CSV.

    Los nombres exactos de los campos del form (ddl*, btn*) deben
    confirmarse inspeccionando el HTML real con DevTools.
"""

import io
import logging
from datetime import date

import httpx
import pandas as pd
from bs4 import BeautifulSoup

from config import HTTP_HEADERS, HTTP_TIMEOUT, SOURCE_NAME_MAP, SOURCE_TYPE_MAP, UTE_BAJADAS_URL
from src.connectors.base import BaseConnector, ConnectorError, ConnectorMetadata

logger = logging.getLogger(__name__)

# Datasets disponibles en UTE Bajadas y sus nombres internos
# Las claves son los valores del dropdown del formulario (a confirmar con DevTools)
UTE_DATASETS = {
    "COMPOSICION_FUENTE":   "composition_by_source",
    "DEMANDA_MIN_MAX":       "demand_min_max",
    "PRODUCCION_HIDRO":      "hydro",
    "PRODUCCION_EOLICA":     "wind",
    "PRODUCCION_SOLAR":      "solar",
    "PRODUCCION_BIOMASA":    "biomass",
    "PRODUCCION_TERMICA":    "thermal",
    "INTERCAMBIOS":          "exchange",
}


class UteBajadasConnector(BaseConnector):
    """
    Descarga series históricas diarias desde el portal SGE Público de UTE.
    """

    def __init__(self, dataset_key: str = "COMPOSICION_FUENTE"):
        """
        Args:
            dataset_key: clave del dataset a descargar (ver UTE_DATASETS).
        """
        if dataset_key not in UTE_DATASETS:
            raise ValueError(
                f"Dataset '{dataset_key}' no reconocido. "
                f"Opciones: {list(UTE_DATASETS.keys())}"
            )
        self.dataset_key = dataset_key
        self.dataset_name = UTE_DATASETS[dataset_key]

    def get_metadata(self) -> ConnectorMetadata:
        return ConnectorMetadata(
            name="ute_bajadas",
            description=f"Series diarias UTE — dataset: {self.dataset_name}",
            base_url=UTE_BAJADAS_URL,
            granularity="daily",
            auth_required=False,
            notes=(
                "Página ASPX con ViewState. Requiere GET inicial + POST. "
                "Confirmar nombres de campos del form con DevTools antes de producción."
            ),
        )

    def fetch(self, date_from: date, date_to: date) -> pd.DataFrame:
        """
        Descarga el dataset seleccionado y lo retorna como DataFrame normalizado.

        Columnas del DataFrame resultante (para datasets de generación):
            date (str), source (str), source_type (str),
            value_mwh (float), data_source (str)
        """
        logger.info(
            "UTE Bajadas [%s]: descargando %s → %s",
            self.dataset_key,
            date_from.isoformat(),
            date_to.isoformat(),
        )

        raw_bytes = self._download_dataset(date_from, date_to)
        df = self._parse_file(raw_bytes)

        if self.dataset_name == "demand_min_max":
            df = self._normalize_demand(df)
        elif self.dataset_name == "exchange":
            df = self._normalize_exchange(df)
        else:
            df = self._normalize_generation(df)

        df["data_source"] = "ute_bajadas"
        logger.info("UTE Bajadas [%s]: %d filas obtenidas.", self.dataset_key, len(df))
        return df

    def validate(self, df: pd.DataFrame) -> bool:
        if df.empty:
            logger.error("UTE Bajadas: DataFrame vacío.")
            return False
        if "date" not in df.columns:
            logger.error("UTE Bajadas: falta columna 'date'.")
            return False
        return True

    # ─── Métodos privados ─────────────────────────────────────────────────────

    def _download_dataset(self, date_from: date, date_to: date) -> bytes:
        """
        Ejecuta el flujo GET → POST para descargar el archivo del formulario ASPX.
        """
        with httpx.Client(timeout=HTTP_TIMEOUT, headers=HTTP_HEADERS) as client:
            # Paso 1: GET para capturar ViewState
            try:
                resp_get = client.get(UTE_BAJADAS_URL)
                resp_get.raise_for_status()
            except httpx.HTTPError as exc:
                raise ConnectorError("ute_bajadas", f"GET inicial falló: {exc}", exc) from exc

            viewstate, event_validation = self._extract_aspnet_tokens(resp_get.text)

            # Paso 2: POST con tokens y parámetros del dataset
            # NOTA: los nombres de campos (ddlTipoArchivo, ddlAnio, etc.)
            # deben confirmarse inspeccionando el form HTML real.
            payload = {
                "__VIEWSTATE":        viewstate,
                "__EVENTVALIDATION":  event_validation,
                "ddlTipoArchivo":     self.dataset_key,
                "txtFechaDesde":      date_from.strftime("%d/%m/%Y"),
                "txtFechaHasta":      date_to.strftime("%d/%m/%Y"),
                "btnDescargar":       "Descargar",
            }

            try:
                resp_post = client.post(UTE_BAJADAS_URL, data=payload)
                resp_post.raise_for_status()
            except httpx.HTTPError as exc:
                raise ConnectorError("ute_bajadas", f"POST falló: {exc}", exc) from exc

            # Verificar que la respuesta es un archivo y no una página de error
            content_type = resp_post.headers.get("content-type", "")
            if "text/html" in content_type and len(resp_post.content) < 50_000:
                raise ConnectorError(
                    "ute_bajadas",
                    "El servidor retornó HTML en lugar del archivo. "
                    "Posiblemente los nombres de campos del formulario cambiaron. "
                    "Verificar con DevTools → Network en el navegador.",
                )

            return resp_post.content

    def _extract_aspnet_tokens(self, html: str) -> tuple[str, str]:
        """Extrae __VIEWSTATE y __EVENTVALIDATION del HTML de la página ASPX."""
        soup = BeautifulSoup(html, "html.parser")

        vs_tag = soup.find("input", {"name": "__VIEWSTATE"})
        ev_tag = soup.find("input", {"name": "__EVENTVALIDATION"})

        if vs_tag is None:
            raise ConnectorError(
                "ute_bajadas",
                "No se encontró __VIEWSTATE en la página. "
                "La estructura del formulario puede haber cambiado.",
            )

        viewstate = vs_tag.get("value", "")
        event_validation = ev_tag.get("value", "") if ev_tag else ""
        return viewstate, event_validation

    def _parse_file(self, content: bytes) -> pd.DataFrame:
        """Intenta leer el contenido como XLSX o CSV."""
        # Intentar XLSX primero
        try:
            return pd.read_excel(io.BytesIO(content), engine="openpyxl")
        except Exception:
            pass
        # Intentar CSV
        try:
            return pd.read_csv(io.BytesIO(content), sep=None, engine="python")
        except Exception as exc:
            raise ConnectorError(
                "ute_bajadas",
                f"No se pudo parsear el archivo como XLSX ni CSV: {exc}",
                exc,
            ) from exc

    def _normalize_generation(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normaliza datasets de generación por fuente al formato largo estándar.
        Retorna columnas: date, source, source_type, value_mwh
        """
        date_col = self._detect_date_col(df)
        if date_col is None:
            raise ConnectorError("ute_bajadas", "No se encontró columna de fecha.")

        # Detectar columnas de valor (todas excepto la de fecha)
        value_cols = [c for c in df.columns if c != date_col]

        df_long = df.melt(
            id_vars=[date_col],
            value_vars=value_cols,
            var_name="source_raw",
            value_name="value_mwh",
        )
        df_long.rename(columns={date_col: "date"}, inplace=True)

        # Normalizar fecha
        df_long["date"] = pd.to_datetime(
            df_long["date"], dayfirst=True, errors="coerce"
        ).dt.strftime("%Y-%m-%d")

        # Normalizar nombre de fuente
        df_long["source"] = (
            df_long["source_raw"]
            .str.lower()
            .str.strip()
            .map(SOURCE_NAME_MAP)
            .fillna(df_long["source_raw"].str.lower().str.strip())
        )
        df_long["source_type"] = df_long["source"].map(SOURCE_TYPE_MAP).fillna("unknown")
        df_long["value_mwh"] = pd.to_numeric(df_long["value_mwh"], errors="coerce")

        return df_long.dropna(subset=["date", "value_mwh"])[
            ["date", "source", "source_type", "value_mwh"]
        ]

    def _normalize_demand(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normaliza el dataset de mínimos y máximos de demanda."""
        date_col = self._detect_date_col(df)
        if date_col is None:
            raise ConnectorError("ute_bajadas", "No se encontró columna de fecha en demanda.")

        df_out = df.rename(columns={date_col: "date"}).copy()
        df_out["date"] = pd.to_datetime(
            df_out["date"], dayfirst=True, errors="coerce"
        ).dt.strftime("%Y-%m-%d")

        # Buscar columnas de min, max y total (nombres aproximados)
        col_map = {}
        for col in df_out.columns:
            col_lower = col.lower()
            if "min" in col_lower:
                col_map["min_mw"] = col
            elif "max" in col_lower:
                col_map["max_mw"] = col
            elif "total" in col_lower or "demanda" in col_lower or "mwh" in col_lower:
                col_map["value_mwh"] = col

        result = pd.DataFrame()
        result["date"] = df_out["date"]
        for key, col in col_map.items():
            result[key] = pd.to_numeric(df_out[col], errors="coerce")

        return result.dropna(subset=["date"])

    def _normalize_exchange(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normaliza el dataset de intercambios internacionales."""
        date_col = self._detect_date_col(df)
        if date_col is None:
            raise ConnectorError("ute_bajadas", "No se encontró columna de fecha en intercambios.")

        value_cols = [c for c in df.columns if c != date_col]
        df_long = df.melt(
            id_vars=[date_col],
            value_vars=value_cols,
            var_name="exchange_col",
            value_name="value_mwh",
        )
        df_long.rename(columns={date_col: "date"}, inplace=True)
        df_long["date"] = pd.to_datetime(
            df_long["date"], dayfirst=True, errors="coerce"
        ).dt.strftime("%Y-%m-%d")
        df_long["granularity"] = "daily"

        # Inferir dirección y país desde nombre de columna
        df_long["direction"] = df_long["exchange_col"].apply(
            lambda x: "import" if "import" in str(x).lower() else "export"
        )
        df_long["country"] = df_long["exchange_col"].apply(_infer_country)
        df_long["value_mwh"] = pd.to_numeric(df_long["value_mwh"], errors="coerce")

        return df_long.dropna(subset=["date", "value_mwh"])[
            ["date", "granularity", "country", "direction", "value_mwh"]
        ]

    def _detect_date_col(self, df: pd.DataFrame) -> str | None:
        """Detecta la columna de fechas en el DataFrame."""
        candidates = ["Fecha", "fecha", "Date", "date", "Día", "Dia", "dia"]
        for c in candidates:
            if c in df.columns:
                return c
        # Buscar por contenido
        for col in df.columns:
            try:
                pd.to_datetime(df[col].dropna().head(3), dayfirst=True)
                return col
            except Exception:
                continue
        return None


def _infer_country(col_name: str) -> str:
    """Infiere el país desde el nombre de columna del dataset de intercambios."""
    name = str(col_name).lower()
    if "argentin" in name:
        return "argentina"
    if "brasil" in name or "brazil" in name:
        return "brasil"
    return "unknown"

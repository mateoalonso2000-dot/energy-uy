"""
adme_precio_spot.py — Conector para el precio spot sancionado de ADME.

Fuente confirmada: https://www.adme.com.uy/panelControl/sancionado_excel.php
Formato: XLSX descargado directamente en la respuesta HTTP.
Granularidad: horaria.

Flujo de acceso (validado con archivo real):
    1. GET sancionado_excel.php con parámetros:
           anod=YYYY         — año de inicio
           anoh=YYYY         — año de fin
           mesd=MM           — mes de inicio (dos dígitos, con cero)
           mesh=MM           — mes de fin (dos dígitos, con cero)
           usd=1             — moneda USD (fijo)
           serie=1           — granularidad horaria (fijo)
           ultimo_anio=YYYY  — último período disponible (calculado con datetime.now())
           ultimo_mes=MM     — último período disponible (calculado con datetime.now())
    2. Leer el XLSX desde el contenido binario de la respuesta (sin guardar a disco).
    3. Procesar la hoja "Spot Sancionado".

Estructura del XLSX (confirmada con archivo real):
    Fila 0:  encabezados directamente (sin fila de título).
    2 columnas:
        "Fecha"                    — formato "DD-MM-YYYY HH:MM"
        "Precio Spot Sancionado"   — USD/MWh, float (puede ser 0, es válido)
    Sin notas al pie.

Diferencias con adme_generacion_mensual.py:
    - Resolución horaria (no mensual).
    - Solo 2 columnas: fecha y precio.
    - Los valores cero son válidos (sobreoferta renovable).
    - Los parámetros ultimo_anio/ultimo_mes se calculan dinámicamente.
"""

import io
import logging
from datetime import date, datetime

import httpx
import pandas as pd

from config import ADME_PRECIO_SPOT_URL, HTTP_HEADERS, HTTP_TIMEOUT
from src.connectors.base import BaseConnector, ConnectorError, ConnectorMetadata

logger = logging.getLogger(__name__)

# Nombre de la hoja esperada en el XLSX
SHEET_NAME = "Spot Sancionado"

# Nombre exacto de las columnas en el XLSX → nombres internos del pipeline
COLUMN_RENAME: dict[str, str] = {
    "Fecha":                            "timestamp",
    "Precio Spot Sancionado (USD/MWh)": "price_usd",
}

# Formato de fecha confirmado en el XLSX
DATETIME_FORMAT = "%d-%m-%Y %H:%M"


class AdmePrecioSpotConnector(BaseConnector):
    """
    Descarga el precio spot sancionado horario del Panel de Control de ADME.

    Retorna un DataFrame con resolución horaria y precio en USD/MWh.

    Columnas del DataFrame resultante:
        datetime (datetime64)   — marca temporal horaria
        precio_spot_usd (float) — precio spot en USD/MWh (0 es válido, nunca negativo)
        data_source (str)       — "adme_precio_spot"

    Índice: RangeIndex (consistente con el resto del pipeline).

    Este conector expone fetch_mensual() como método principal con parámetros
    enteros de año/mes, y fetch() como adaptador de la firma estándar
    BaseConnector.
    """

    def get_metadata(self) -> ConnectorMetadata:
        return ConnectorMetadata(
            name="adme_precio_spot",
            description="Precio spot sancionado horario en USD/MWh desde Panel de Control ADME",
            base_url=ADME_PRECIO_SPOT_URL,
            granularity="hourly",
            auth_required=False,
            notes=(
                "GET a /panelControl/sancionado_excel.php con params anod/anoh/mesd/mesh. "
                "usd=1 (USD), serie=1 (horaria). "
                "ultimo_anio/ultimo_mes calculados con datetime.now(). "
                "Hoja usada: 'Spot Sancionado'. Unidades: USD/MWh."
            ),
        )

    def fetch(self, date_from: date, date_to: date) -> pd.DataFrame:
        """
        Adaptador de la firma estándar BaseConnector → fetch_mensual().

        Extrae año y mes de las fechas de inicio y fin y delega al método
        principal fetch_mensual().
        """
        return self.fetch_mensual(
            anio_desde=date_from.year,
            mes_desde=date_from.month,
            anio_hasta=date_to.year,
            mes_hasta=date_to.month,
        )

    def fetch_mensual(
        self,
        anio_desde: int,
        mes_desde: int,
        anio_hasta: int,
        mes_hasta: int,
    ) -> pd.DataFrame:
        """
        Descarga y procesa el precio spot sancionado para el período indicado.

        Args:
            anio_desde: año de inicio (ej: 2024)
            mes_desde:  mes de inicio, 1–12 (ej: 1 para enero)
            anio_hasta: año de fin (ej: 2024)
            mes_hasta:  mes de fin, 1–12 (ej: 12 para diciembre)

        Returns:
            DataFrame con columnas datetime, precio_spot_usd, data_source.
            Resolución horaria. Índice RangeIndex.

        Raises:
            ConnectorError: si la descarga o el parseo falla.
        """
        logger.info(
            "ADME Precio Spot: descargando %d/%02d → %d/%02d",
            anio_desde, mes_desde, anio_hasta, mes_hasta,
        )

        xlsx_bytes = self._download_xlsx(anio_desde, mes_desde, anio_hasta, mes_hasta)
        df         = self._parse_sheet(xlsx_bytes)
        df         = self._rename_and_clean(df)

        df["data_source"] = "adme_precio_spot"

        logger.info("ADME Precio Spot: %d filas obtenidas.", len(df))
        return df

    def validate(self, df: pd.DataFrame) -> bool:
        """Verifica que el DataFrame tiene la estructura mínima esperada."""
        required = {"timestamp", "price_usd", "data_source"}
        missing  = required - set(df.columns)
        if missing:
            logger.error("ADME Precio Spot: columnas faltantes: %s", missing)
            return False
        if df.empty:
            logger.error("ADME Precio Spot: DataFrame vacío.")
            return False
        if df["price_usd"].isna().all():
            logger.error("ADME Precio Spot: todos los valores de price_usd son NaN.")
            return False
        return True

    # ─── Pasos privados del flujo ─────────────────────────────────────────────

    def _download_xlsx(
        self,
        anio_desde: int,
        mes_desde: int,
        anio_hasta: int,
        mes_hasta: int,
    ) -> bytes:
        """
        Paso 1 — GET a sancionado_excel.php con los parámetros de año/mes.

        ultimo_anio y ultimo_mes se calculan con datetime.now() en el momento
        de la llamada para reflejar el último período disponible.

        Returns:
            Contenido del archivo XLSX como bytes.
        """
        now = datetime.now()
        params = {
            "anod":        anio_desde,
            "anoh":        anio_hasta,
            "mesd":        f"{mes_desde:02d}",
            "mesh":        f"{mes_hasta:02d}",
            "usd":         1,
            "serie":       1,
            "ultimo_anio": now.year,
            "ultimo_mes":  f"{now.month:02d}",
        }

        logger.debug(
            "ADME Precio Spot: GET %s params=%s",
            ADME_PRECIO_SPOT_URL, params,
        )

        try:
            with httpx.Client(timeout=HTTP_TIMEOUT, headers=HTTP_HEADERS) as client:
                resp = client.get(ADME_PRECIO_SPOT_URL, params=params)
                resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ConnectorError(
                "adme_precio_spot",
                f"El servidor respondió con HTTP {exc.response.status_code} "
                f"al consultar sancionado_excel.php para el período "
                f"{anio_desde}/{mes_desde:02d} → {anio_hasta}/{mes_hasta:02d}.",
                original=exc,
            ) from exc
        except httpx.HTTPError as exc:
            raise ConnectorError(
                "adme_precio_spot",
                f"Error de red al consultar sancionado_excel.php: {exc}",
                original=exc,
            ) from exc

        if not resp.content:
            raise ConnectorError(
                "adme_precio_spot",
                "La respuesta de sancionado_excel.php está vacía. "
                "Es posible que no haya datos para el período solicitado.",
            )

        logger.debug(
            "ADME Precio Spot: XLSX descargado (%d bytes).",
            len(resp.content),
        )
        return resp.content

    def _parse_sheet(self, xlsx_bytes: bytes) -> pd.DataFrame:
        """
        Paso 2 — Lee la hoja "Spot Sancionado" del XLSX.

        No hay filas de título ni notas al pie: fila 0 son directamente
        los encabezados y todas las filas siguientes son datos.

        Returns:
            DataFrame crudo con las columnas originales del XLSX.
        """
        try:
            df = pd.read_excel(
                io.BytesIO(xlsx_bytes),
                engine="openpyxl",
                sheet_name=SHEET_NAME,
                header=0,
            )
        except Exception as exc:
            raise ConnectorError(
                "adme_precio_spot",
                f"No se pudo leer la hoja '{SHEET_NAME}' del XLSX: {exc}",
                original=exc,
            ) from exc

        if df.empty:
            raise ConnectorError(
                "adme_precio_spot",
                f"La hoja '{SHEET_NAME}' del XLSX está vacía.",
            )

        # Verificar que las dos columnas esperadas están presentes
        missing_cols = set(COLUMN_RENAME.keys()) - set(df.columns)
        if missing_cols:
            raise ConnectorError(
                "adme_precio_spot",
                f"Columnas esperadas no encontradas en la hoja '{SHEET_NAME}': "
                f"{missing_cols}. La estructura del XLSX puede haber cambiado.",
            )

        logger.debug(
            "ADME Precio Spot: hoja '%s' parseada — %d filas.",
            SHEET_NAME, len(df),
        )
        return df

    def _rename_and_clean(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Paso 3 — Renombra columnas y limpia tipos de datos.

        - Renombra "Fecha" → "datetime" y "Precio Spot Sancionado" → "precio_spot_usd".
        - Parsea "datetime" del formato "DD-MM-YYYY HH:MM" a datetime64.
        - Fuerza "precio_spot_usd" a float64.
        - Descarta filas donde "datetime" no se pudo parsear.
        - Registra advertencia si hay valores negativos en precio_spot_usd
          (no los descarta, pero no deberían existir en datos reales).

        Returns:
            DataFrame limpio con tipos correctos. Índice RangeIndex.
        """
        df = df.rename(columns=COLUMN_RENAME)

        # Parsear fecha/hora del formato confirmado "DD-MM-YYYY HH:MM"
        df["timestamp"] = pd.to_datetime(
            df["timestamp"],
            format=DATETIME_FORMAT,
            errors="coerce",
        )

        # Descartar filas con timestamp inválido
        n_before = len(df)
        df = df.dropna(subset=["timestamp"])
        if len(df) < n_before:
            logger.debug(
                "ADME Precio Spot: %d filas con timestamp inválido descartadas.",
                n_before - len(df),
            )

        # Forzar precio a float64
        df["price_usd"] = pd.to_numeric(df["price_usd"], errors="coerce")

        # Advertir (no descartar) si hay valores negativos — no deberían existir
        n_negativos = (df["price_usd"] < 0).sum()
        if n_negativos > 0:
            logger.warning(
                "ADME Precio Spot: %d filas con price_usd negativo encontradas. "
                "Verificar la fuente.",
                n_negativos,
            )

        return df.reset_index(drop=True)

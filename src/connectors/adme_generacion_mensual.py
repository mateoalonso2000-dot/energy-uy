"""
adme_generacion_mensual.py — Conector para la generación mensual por fuente de ADME.

Fuente confirmada: https://adme.com.uy/panelControl/gpf_excel.php
Formato: XLSX descargado directamente en la respuesta HTTP.
Granularidad: mensual.

Flujo de acceso (validado con archivo real):
    1. GET gpf_excel.php con parámetros:
           anod=YYYY   — año de inicio
           anoh=YYYY   — año de fin
           mesd=MM     — mes de inicio (dos dígitos, con cero)
           mesh=MM     — mes de fin (dos dígitos, con cero)
           periodo=3   — granularidad mensual
           fuente=1    — generación por fuente
           tipo=0      — fijo
    2. Leer el XLSX desde el contenido binario de la respuesta (sin guardar a disco).
    3. Procesar la única hoja: "Agrupado por recurso".

Estructura del XLSX (confirmada con archivo real):
    Fila 0:  encabezados (no hay fila de título).
    Columna "Fecha": formato MM-YYYY (ej: "01-2024").
    Columnas de datos (MWh):
        Hidráulica Inyec, Hidráulica Extrac,
        Biomasa Inyec, Biomasa Extrac,
        Térmico Inyec, Térmico Extrac,
        Eólico Inyec, Eólico Extrac,
        Solar Inyec, Solar Extrac,
        Importaciones, Exportaciones,
        Demanda Bruta, Demanda Neta
    Últimas filas: notas al pie en texto libre — todas las columnas numéricas son NaN.

Diferencias con adme_scada.py:
    - Unidades: MWh (no MW).
    - Parámetros de fecha distintos (año/mes separados, no rango de días).
    - Formato de salida: ancho (una columna por fuente) en lugar de largo.
    - Se calculan columnas netas (inyec − extrac) para las 5 fuentes que las tienen.
"""

import io
import logging
from datetime import date

import httpx
import pandas as pd

from config import ADME_GENERACION_MENSUAL_URL, HTTP_HEADERS, HTTP_TIMEOUT
from src.connectors.base import BaseConnector, ConnectorError, ConnectorMetadata

logger = logging.getLogger(__name__)

# ─── Mapeo de columnas XLSX → nombres snake_case internos ────────────────────
# Clave: nombre exacto en el XLSX | Valor: nombre interno del pipeline
COLUMN_RENAME: dict[str, str] = {
    "Fecha":             "fecha",
    "Hidráulica Inyec":  "hidraulica_inyec",
    "Hidráulica Extrac": "hidraulica_extrac",
    "Biomasa Inyec":     "biomasa_inyec",
    "Biomasa Extrac":    "biomasa_extrac",
    "Térmico Inyec":     "termico_inyec",
    "Térmico Extrac":    "termico_extrac",
    "Eólico Inyec":      "eolico_inyec",
    "Eólico Extrac":     "eolico_extrac",
    "Solar Inyec":       "solar_inyec",
    "Solar Extrac":      "solar_extrac",
    "Importaciones":     "importaciones",
    "Exportaciones":     "exportaciones",
    "Demanda Bruta":     "demanda_bruta",
    "Demanda Neta":      "demanda_neta",
}

# Pares de columnas para calcular valores netos: (inyec, extrac) → neta
NET_COLUMNS: list[tuple[str, str, str]] = [
    ("hidraulica_inyec", "hidraulica_extrac", "hidraulica_neta"),
    ("biomasa_inyec",    "biomasa_extrac",    "biomasa_neta"),
    ("termico_inyec",    "termico_extrac",    "termico_neta"),
    ("eolico_inyec",     "eolico_extrac",     "eolico_neta"),
    ("solar_inyec",      "solar_extrac",      "solar_neta"),
]

# Columnas que deben ser numéricas (todas excepto fecha)
NUMERIC_COLUMNS = [v for v in COLUMN_RENAME.values() if v != "fecha"]

# Nombre de la hoja esperada
SHEET_NAME = "Agrupado por recurso"


class AdmeGeneracionMensualConnector(BaseConnector):
    """
    Descarga generación mensual por fuente del Panel de Control de ADME.

    Retorna un DataFrame en formato ancho con una columna por fuente de energía.
    Las columnas de valor están en MWh.

    Columnas del DataFrame resultante:
        fecha (datetime64)       — primer día del mes
        hidraulica_inyec         — MWh inyectados por hidráulica
        hidraulica_extrac        — MWh extraídos (bombeo)
        hidraulica_neta          — inyec − extrac (calculada)
        biomasa_inyec / _extrac / _neta
        termico_inyec / _extrac / _neta
        eolico_inyec / _extrac / _neta
        solar_inyec / _extrac / _neta
        importaciones            — MWh importados
        exportaciones            — MWh exportados
        demanda_bruta            — MWh demanda bruta
        demanda_neta             — MWh demanda neta
        data_source              — "adme_generacion_mensual"

    Este conector NO usa la firma date_from/date_to de BaseConnector porque
    los parámetros de la fuente son año/mes enteros. Se implementa fetch()
    con la firma estándar como alias, y se expone fetch_mensual() como
    método principal con parámetros más descriptivos.
    """

    def get_metadata(self) -> ConnectorMetadata:
        return ConnectorMetadata(
            name="adme_generacion_mensual",
            description="Generación mensual por fuente desde Panel de Control ADME",
            base_url=ADME_GENERACION_MENSUAL_URL,
            granularity="monthly",
            auth_required=False,
            notes=(
                "GET a /panelControl/gpf_excel.php con params anod/anoh/mesd/mesh. "
                "periodo=3 (mensual), fuente=1 (generación por fuente), tipo=0. "
                "Hoja usada: 'Agrupado por recurso'. Unidades: MWh."
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
        Descarga y procesa datos de generación mensual para el período indicado.

        Args:
            anio_desde: año de inicio (ej: 2024)
            mes_desde:  mes de inicio, 1–12 (ej: 1 para enero)
            anio_hasta: año de fin (ej: 2024)
            mes_hasta:  mes de fin, 1–12 (ej: 12 para diciembre)

        Returns:
            DataFrame ancho con columnas fecha + generación por fuente en MWh,
            más columnas netas calculadas. Índice RangeIndex.

        Raises:
            ConnectorError: si la descarga o el parseo falla.
        """
        logger.info(
            "ADME Generación Mensual: descargando %d/%02d → %d/%02d",
            anio_desde, mes_desde, anio_hasta, mes_hasta,
        )

        xlsx_bytes = self._download_xlsx(anio_desde, mes_desde, anio_hasta, mes_hasta)
        df         = self._parse_sheet(xlsx_bytes)
        df         = self._rename_and_clean(df)
        df         = self._add_net_columns(df)

        df["data_source"] = "adme_generacion_mensual"

        logger.info("ADME Generación Mensual: %d filas obtenidas.", len(df))
        return df

    def validate(self, df: pd.DataFrame) -> bool:
        """Verifica que el DataFrame tiene la estructura mínima esperada."""
        required = {"fecha", "demanda_neta", "data_source"}
        missing  = required - set(df.columns)
        if missing:
            logger.error("ADME Generación Mensual: columnas faltantes: %s", missing)
            return False
        if df.empty:
            logger.error("ADME Generación Mensual: DataFrame vacío.")
            return False
        if df["demanda_neta"].isna().all():
            logger.error("ADME Generación Mensual: todos los valores de demanda_neta son NaN.")
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
        Paso 1 — GET a gpf_excel.php con los parámetros de año/mes.

        Los meses se formatean con cero adelante (01, 02, … 12).

        Returns:
            Contenido del archivo XLSX como bytes.
        """
        params = {
            "anod":    anio_desde,
            "anoh":    anio_hasta,
            "mesd":    f"{mes_desde:02d}",
            "mesh":    f"{mes_hasta:02d}",
            "periodo": 3,
            "fuente":  1,
            "tipo":    0,
        }

        logger.debug(
            "ADME Generación Mensual: GET %s params=%s",
            ADME_GENERACION_MENSUAL_URL, params,
        )

        try:
            with httpx.Client(timeout=HTTP_TIMEOUT, headers=HTTP_HEADERS) as client:
                resp = client.get(ADME_GENERACION_MENSUAL_URL, params=params)
                resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ConnectorError(
                "adme_generacion_mensual",
                f"El servidor respondió con HTTP {exc.response.status_code} "
                f"al consultar gpf_excel.php para el período "
                f"{anio_desde}/{mes_desde:02d} → {anio_hasta}/{mes_hasta:02d}.",
                original=exc,
            ) from exc
        except httpx.HTTPError as exc:
            raise ConnectorError(
                "adme_generacion_mensual",
                f"Error de red al consultar gpf_excel.php: {exc}",
                original=exc,
            ) from exc

        if not resp.content:
            raise ConnectorError(
                "adme_generacion_mensual",
                "La respuesta de gpf_excel.php está vacía. "
                "Es posible que no haya datos para el período solicitado.",
            )

        logger.debug(
            "ADME Generación Mensual: XLSX descargado (%d bytes).",
            len(resp.content),
        )
        return resp.content

    def _parse_sheet(self, xlsx_bytes: bytes) -> pd.DataFrame:
        """
        Paso 2 — Lee la hoja "Agrupado por recurso" del XLSX.

        Descarta las filas de notas al pie: son las filas donde todas
        las columnas numéricas conocidas tienen NaN.

        Returns:
            DataFrame crudo con las columnas originales del XLSX (sin renombrar).
        """
        try:
            df = pd.read_excel(
                io.BytesIO(xlsx_bytes),
                engine="openpyxl",
                sheet_name=SHEET_NAME,
                header=0,    # fila 0 son los encabezados (no hay título)
            )
        except Exception as exc:
            raise ConnectorError(
                "adme_generacion_mensual",
                f"No se pudo leer la hoja '{SHEET_NAME}' del XLSX: {exc}",
                original=exc,
            ) from exc

        if df.empty:
            raise ConnectorError(
                "adme_generacion_mensual",
                f"La hoja '{SHEET_NAME}' del XLSX está vacía.",
            )

        # Identificar las columnas numéricas reales presentes en el DataFrame
        # (excluye "Fecha" y cualquier columna extra desconocida)
        known_numeric_cols = [
            col for col in df.columns
            if col in COLUMN_RENAME and col != "Fecha"
        ]

        if not known_numeric_cols:
            raise ConnectorError(
                "adme_generacion_mensual",
                "No se encontraron columnas numéricas conocidas en el XLSX. "
                "La estructura del archivo puede haber cambiado.",
            )

        # Descartar filas footer: todas las columnas numéricas conocidas son NaN
        n_before = len(df)
        mask_footer = df[known_numeric_cols].isna().all(axis=1)
        df = df[~mask_footer].copy()

        if len(df) < n_before:
            logger.debug(
                "ADME Generación Mensual: %d filas de notas al pie descartadas.",
                n_before - len(df),
            )

        if df.empty:
            raise ConnectorError(
                "adme_generacion_mensual",
                "El XLSX solo contiene filas de notas al pie — no hay datos reales.",
            )

        logger.debug(
            "ADME Generación Mensual: hoja '%s' parseada — %d filas, %d columnas.",
            SHEET_NAME, len(df), len(df.columns),
        )
        return df

    def _rename_and_clean(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Paso 3 — Renombra columnas a snake_case y limpia tipos de datos.

        - Renombra usando COLUMN_RENAME (solo columnas presentes en el DataFrame).
        - Parsea la columna "fecha" de formato "MM-YYYY" al primer día del mes.
        - Fuerza las columnas numéricas conocidas a float64.
        - Descarta filas donde "fecha" no se pudo parsear.

        Returns:
            DataFrame con columnas renombradas, fecha como datetime64, valores float.
        """
        # Renombrar solo las columnas que existen
        rename_map = {k: v for k, v in COLUMN_RENAME.items() if k in df.columns}
        df = df.rename(columns=rename_map)

        # Verificar que la columna fecha está presente tras el renombrado
        if "fecha" not in df.columns:
            raise ConnectorError(
                "adme_generacion_mensual",
                "No se encontró la columna 'Fecha' en el XLSX. "
                "La estructura del archivo puede haber cambiado.",
            )

        # Parsear "MM-YYYY" → primer día del mes como datetime64
        # Ejemplo: "01-2024" → datetime(2024, 1, 1)
        df["fecha"] = pd.to_datetime(
            df["fecha"],
            format="%m-%Y",
            errors="coerce",
        )

        # Descartar filas con fecha inválida (ej: si quedaron notas inesperadas)
        n_before = len(df)
        df = df.dropna(subset=["fecha"])
        if len(df) < n_before:
            logger.debug(
                "ADME Generación Mensual: %d filas con fecha inválida descartadas.",
                n_before - len(df),
            )

        # Forzar columnas numéricas a float64
        for col in NUMERIC_COLUMNS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Advertir sobre columnas esperadas que no aparecen en el XLSX
        expected_internal = set(COLUMN_RENAME.values()) - {"fecha"}
        present_internal  = set(df.columns) & expected_internal
        missing_internal  = expected_internal - present_internal
        if missing_internal:
            logger.warning(
                "ADME Generación Mensual: columnas esperadas no encontradas en el XLSX: %s. "
                "La estructura del archivo puede haber cambiado.",
                missing_internal,
            )

        return df.reset_index(drop=True)

    def _add_net_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Paso 4 — Calcula columnas netas (inyec − extrac) para cada fuente.

        Solo calcula la columna neta si ambas columnas (inyec y extrac)
        están presentes en el DataFrame. Si falta alguna, registra un warning
        y omite esa columna neta.

        Las columnas netas se insertan inmediatamente después de la columna
        _extrac correspondiente para facilitar la lectura.

        Returns:
            DataFrame con columnas netas agregadas.
        """
        for col_inyec, col_extrac, col_neta in NET_COLUMNS:
            if col_inyec in df.columns and col_extrac in df.columns:
                df[col_neta] = df[col_inyec] - df[col_extrac]
                logger.debug(
                    "ADME Generación Mensual: columna neta calculada: %s", col_neta
                )
            else:
                missing = [c for c in (col_inyec, col_extrac) if c not in df.columns]
                logger.warning(
                    "ADME Generación Mensual: no se puede calcular %s, "
                    "faltan columnas: %s",
                    col_neta, missing,
                )

        return df

"""
adme_scada.py — Conector para el SCADA GPF de ADME.

Fuente confirmada: https://pronos.adme.com.uy/gpf.php
Formato: archivo ODS descargado desde un link embebido en la respuesta HTML.
Granularidad: horaria.

Flujo de acceso (validado con pruebas reales):
    1. GET gpf.php?fecha_ini=D/M/YYYY&fecha_fin=D/M/YYYY&send=MOSTRAR
    2. Parsear el HTML de respuesta con BeautifulSoup para extraer la URL
       del archivo ODS (patrón: href con "/cache/" y ".ods").
    3. GET a la URL absoluta del ODS.
    4. Leer la hoja "GPF" con pandas (skiprows=2 para saltear los 2 títulos).

Estructura del ODS (confirmada):
    Fila 0:  título SCADA (se omite con skiprows=2)
    Fila 1:  descripción (se omite con skiprows=2)
    Fila 1:  encabezados — Fecha, Salto Grande, Bonete, Baygorria, Palmar,
             Eólica, Solar, Térmica, Biomasa, Imp.Arg, Imp.Br.Riv, Imp.Br.Mel, Demanda
    Fila 2+: datos horarios en MW
"""

import io
import logging
from datetime import date
from urllib.parse import urlparse

import httpx
import pandas as pd
from bs4 import BeautifulSoup

from config import ADME_GPF_BASE_URL, ADME_GPF_URL, HTTP_HEADERS, HTTP_TIMEOUT, SOURCE_TYPE_MAP
from src.connectors.base import BaseConnector, ConnectorError, ConnectorMetadata

# Dominios permitidos para la descarga del ODS (evita SSRF si ADME responde con HTML manipulado)
_ALLOWED_ODS_HOSTS = frozenset({
    urlparse(ADME_GPF_BASE_URL).netloc,   # pronos.adme.com.uy
    "adme.com.uy",
    "www.adme.com.uy",
})

logger = logging.getLogger(__name__)

# ─── Mapeo de columnas ODS → nombres canónicos internos ──────────────────────
# Clave: nombre exacto en el ODS | Valor: nombre snake_case interno
COLUMN_RENAME: dict[str, str] = {
    "Fecha":        "timestamp",
    "Salto Grande": "salto_grande",
    "Bonete":       "bonete",
    "Baygorria":    "baygorria",
    "Palmar":       "palmar",
    "Eólica":       "wind",
    "Solar":        "solar",
    "Térmica":      "thermal",
    "Biomasa":      "biomass",
    "Imp.Arg":      "imp_arg",
    "Imp.Br.Riv":   "imp_br_riv",
    "Imp.Br.Mel":   "imp_br_mel",
    "Demanda":      "demand",
}

# Columnas de generación/intercambio que se convierten a formato largo.
# Cada entrada: nombre_interno → (source, source_type, plant_name)
COLUMN_SOURCE_MAP: dict[str, tuple[str, str, str | None]] = {
    "salto_grande": ("hydro",   "renewable",     "salto_grande"),
    "bonete":       ("hydro",   "renewable",     "bonete"),
    "baygorria":    ("hydro",   "renewable",     "baygorria"),
    "palmar":       ("hydro",   "renewable",     "palmar"),
    "wind":         ("wind",    "renewable",     None),
    "solar":        ("solar",   "renewable",     None),
    "thermal":      ("thermal", "non_renewable", None),
    "biomass":      ("biomass", "renewable",     None),
    "imp_arg":      ("import",  "external",      "argentina"),
    "imp_br_riv":   ("import",  "external",      "brasil_rivera"),
    "imp_br_mel":   ("import",  "external",      "brasil_melo"),
    # "demand" is excluded — it's system demand, not a generation source
}

# Columnas esperadas en el ODS (para validación)
EXPECTED_COLUMNS = set(COLUMN_RENAME.keys())


class AdmeScadaConnector(BaseConnector):
    """
    Descarga generación horaria del SCADA GPF de ADME.

    Retorna un DataFrame en formato largo con columnas:
        timestamp (str ISO8601), source (str), source_type (str),
        plant_name (str | None), value_mw (float), data_source (str)

    Este formato es compatible con clean_generation_hourly() del módulo
    de procesamiento sin ninguna transformación adicional.
    """

    def get_metadata(self) -> ConnectorMetadata:
        return ConnectorMetadata(
            name="adme_scada",
            description="Generación horaria SCADA GPF desde pronos.adme.com.uy",
            base_url=ADME_GPF_URL,
            granularity="hourly",
            auth_required=False,
            notes=(
                "GET a gpf.php → HTML con link a ODS en /cache/. "
                "Parámetros: fecha_ini y fecha_fin en formato D/M/YYYY. "
                "Hoja usada: GPF. Incluye hidro por central, eólica, solar, "
                "térmica, biomasa, importaciones y demanda."
            ),
        )

    def fetch(self, date_from: date, date_to: date) -> pd.DataFrame:
        """
        Descarga y procesa los datos del SCADA para el rango de fechas indicado.

        Args:
            date_from: fecha de inicio (inclusive)
            date_to:   fecha de fin (inclusive)

        Returns:
            DataFrame largo con columnas:
            timestamp, source, source_type, plant_name, value_mw, data_source

        Raises:
            ConnectorError: si la descarga o el parseo falla.
        """
        logger.info(
            "ADME SCADA GPF: descargando %s → %s",
            date_from.isoformat(),
            date_to.isoformat(),
        )

        html      = self._request_gpf_page(date_from, date_to)
        ods_url   = self._extract_ods_url(html)
        ods_bytes = self._download_ods(ods_url)
        df_wide   = self._parse_gpf_sheet(ods_bytes)
        df_long   = self._to_long_format(df_wide)

        df_long["data_source"] = "adme_scada"

        logger.info("ADME SCADA GPF: %d filas obtenidas.", len(df_long))
        return df_long

    def validate(self, df: pd.DataFrame) -> bool:
        """Verifica que el DataFrame tiene la estructura mínima esperada."""
        required = {"timestamp", "source", "source_type", "value_mw", "data_source"}
        missing  = required - set(df.columns)
        if missing:
            logger.error("ADME SCADA: columnas faltantes: %s", missing)
            return False
        if df.empty:
            logger.error("ADME SCADA: DataFrame vacío.")
            return False
        if df["value_mw"].isna().all():
            logger.error("ADME SCADA: todos los valores de value_mw son NaN.")
            return False
        return True

    # ─── Pasos privados del flujo ─────────────────────────────────────────────

    def _request_gpf_page(self, date_from: date, date_to: date) -> str:
        """
        Paso 1 — GET a gpf.php con los parámetros de fecha.

        Las fechas se formatean como D/M/YYYY (sin ceros a la izquierda),
        que es el formato que acepta el servidor de ADME.

        Returns:
            Contenido HTML de la respuesta como string.
        """
        params = {
            "fecha_ini": f"{date_from.day}/{date_from.month}/{date_from.year}",  # D/M/YYYY sin ceros
            "fecha_fin": f"{date_to.day}/{date_to.month}/{date_to.year}",
            "send":      "MOSTRAR",
        }

        logger.debug("ADME GPF: GET %s params=%s", ADME_GPF_URL, params)

        try:
            with httpx.Client(timeout=HTTP_TIMEOUT, headers=HTTP_HEADERS) as client:
                resp = client.get(ADME_GPF_URL, params=params)
                resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ConnectorError(
                "adme_scada",
                f"El servidor respondió con HTTP {exc.response.status_code} "
                f"al consultar gpf.php para el período {date_from} → {date_to}.",
                original=exc,
            ) from exc
        except httpx.HTTPError as exc:
            raise ConnectorError(
                "adme_scada",
                f"Error de red al consultar gpf.php: {exc}",
                original=exc,
            ) from exc

        return resp.text

    def _extract_ods_url(self, html: str) -> str:
        """
        Paso 2 — Parsea el HTML para encontrar el link al archivo ODS.

        El servidor embebe en el HTML un anchor del tipo:
            <a href="/cache/gpf_XXXXX_XXXXX_horario.ods">...</a>

        Returns:
            URL absoluta del archivo ODS.

        Raises:
            ConnectorError: si no se encuentra ningún link .ods en el HTML.
        """
        soup = BeautifulSoup(html, "html.parser")

        # Buscar todos los anchors cuyo href contenga /cache/ y termine en .ods
        ods_links = [
            tag["href"]
            for tag in soup.find_all("a", href=True)
            if "/cache/" in tag["href"] and tag["href"].endswith(".ods")
        ]

        if not ods_links:
            # Guardar el HTML para facilitar el diagnóstico
            snippet = html[:500].replace("\n", " ")
            raise ConnectorError(
                "adme_scada",
                "No se encontró ningún link a archivo .ods en la respuesta de gpf.php. "
                f"Primeros 500 caracteres del HTML: {snippet!r}",
            )

        # Si hay más de uno, preferir el link horario sobre el de 10 minutos
        horario_links = [l for l in ods_links if "_horario" in l]
        ods_path = horario_links[0] if horario_links else ods_links[0]
        if len(ods_links) > 1:
            logger.info(
                "ADME GPF: se encontraron %d links .ods, usando: %s",
                len(ods_links),
                ods_path,
            )

        # Construir URL absoluta
        if ods_path.startswith("http"):
            ods_url = ods_path
        else:
            ods_url = f"{ADME_GPF_BASE_URL}{ods_path}"

        # Validar que el host pertenece a dominios conocidos de ADME (previene SSRF)
        parsed_host = urlparse(ods_url).netloc
        if parsed_host not in _ALLOWED_ODS_HOSTS:
            raise ConnectorError(
                "adme_scada",
                f"La URL del ODS apunta a un dominio inesperado: '{parsed_host}'. "
                f"Se esperaba uno de: {sorted(_ALLOWED_ODS_HOSTS)}. "
                "Verificá que el servidor de ADME no haya sido comprometido.",
            )

        logger.debug("ADME GPF: URL del ODS extraída: %s", ods_url)
        return ods_url

    def _download_ods(self, ods_url: str) -> bytes:
        """
        Paso 3 — Descarga el archivo ODS desde la URL provista.

        Returns:
            Contenido del archivo ODS como bytes.
        """
        logger.debug("ADME GPF: descargando ODS desde %s", ods_url)

        try:
            with httpx.Client(timeout=HTTP_TIMEOUT, headers=HTTP_HEADERS) as client:
                resp = client.get(ods_url)
                resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ConnectorError(
                "adme_scada",
                f"HTTP {exc.response.status_code} al descargar el ODS desde {ods_url}.",
                original=exc,
            ) from exc
        except httpx.HTTPError as exc:
            raise ConnectorError(
                "adme_scada",
                f"Error de red al descargar el ODS: {exc}",
                original=exc,
            ) from exc

        logger.debug("ADME GPF: ODS descargado (%d bytes).", len(resp.content))
        return resp.content

    def _parse_gpf_sheet(self, ods_bytes: bytes) -> pd.DataFrame:
        """
        Paso 4 — Lee la hoja "GPF" del ODS y retorna un DataFrame ancho.

        Estructura del ODS:
            - Fila 0: título con timestamp SCADA (se omite)
            - Fila 1: descripción (se omite)
            - Fila 2: encabezados de columnas
            - Fila 3+: datos horarios

        Renombra columnas al vocabulario canónico interno (snake_case).
        Convierte la columna timestamp a datetime y los valores a float.

        Returns:
            DataFrame ancho con una columna por fuente de energía, más
            la columna "timestamp" como datetime64.
        """
        try:
            df = pd.read_excel(
                io.BytesIO(ods_bytes),
                engine="odf",
                sheet_name="GPF",
                skiprows=2,      # filas 0-1 son títulos
                header=0,        # fila 2 (después del skip) es el header
            )
        except Exception as exc:
            raise ConnectorError(
                "adme_scada",
                f"No se pudo leer la hoja 'GPF' del ODS: {exc}",
                original=exc,
            ) from exc

        if df.empty:
            raise ConnectorError(
                "adme_scada",
                "La hoja 'GPF' del ODS está vacía.",
            )

        # Verificar que las columnas esperadas están presentes
        actual_cols   = set(df.columns)
        missing_cols  = EXPECTED_COLUMNS - actual_cols
        if missing_cols:
            logger.warning(
                "ADME GPF: columnas no encontradas en el ODS: %s. "
                "La estructura del archivo puede haber cambiado.",
                missing_cols,
            )

        # Renombrar solo las columnas que existen en el DataFrame
        rename_map = {k: v for k, v in COLUMN_RENAME.items() if k in actual_cols}
        df = df.rename(columns=rename_map)

        # Parsear timestamp
        if "timestamp" not in df.columns:
            raise ConnectorError(
                "adme_scada",
                "No se encontró la columna 'Fecha' en la hoja GPF. "
                "La estructura del ODS puede haber cambiado.",
            )

        df["timestamp"] = pd.to_datetime(df["timestamp"], format="%Y-%m-%d %H:%M:%S", errors="coerce")

        # Eliminar filas sin timestamp válido (filas de totales, espacios, etc.)
        n_before = len(df)
        df = df.dropna(subset=["timestamp"])
        if len(df) < n_before:
            logger.debug(
                "ADME GPF: %d filas sin timestamp válido eliminadas.",
                n_before - len(df),
            )

        # Convertir columnas de valores a float
        value_cols = [c for c in df.columns if c != "timestamp"]
        for col in value_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        logger.debug(
            "ADME GPF: hoja GPF parseada — %d filas, %d columnas.",
            len(df),
            len(df.columns),
        )
        return df

    def _to_long_format(self, df_wide: pd.DataFrame) -> pd.DataFrame:
        """
        Paso 5 — Convierte el DataFrame ancho a formato largo.

        Cada fila del formato ancho (una columna por fuente) se expande en
        N filas (una por fuente), con las columnas:
            timestamp, source, source_type, plant_name, value_mw

        Las columnas del ODS que no están en COLUMN_SOURCE_MAP se ignoran.

        Returns:
            DataFrame largo con columnas:
            timestamp (str ISO8601), source, source_type, plant_name, value_mw
        """
        frames = []

        for col_name, (source, source_type, plant_name) in COLUMN_SOURCE_MAP.items():
            if col_name not in df_wide.columns:
                logger.debug("ADME GPF: columna '%s' no encontrada, se omite.", col_name)
                continue

            df_col = pd.DataFrame({
                "timestamp":   df_wide["timestamp"],
                "source":      source,
                "source_type": source_type,
                "plant_name":  plant_name,
                "value_mw":    df_wide[col_name],
            })

            frames.append(df_col)

        if not frames:
            raise ConnectorError(
                "adme_scada",
                "No se pudo construir el formato largo: ninguna columna de valor "
                "del ODS coincide con el mapeo esperado.",
            )

        df_long = pd.concat(frames, ignore_index=True)

        # Convertir timestamp a string ISO8601 (formato estándar del pipeline)
        df_long["timestamp"] = df_long["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S")

        # Eliminar filas con valor nulo
        df_long = df_long.dropna(subset=["value_mw"])

        return df_long.reset_index(drop=True)

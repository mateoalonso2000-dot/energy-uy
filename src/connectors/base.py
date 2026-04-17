"""
base.py — Interfaz base que deben implementar todos los conectores.

Cualquier fuente de datos nueva (URSEA, REI, otra entidad) solo necesita
heredar de BaseConnector e implementar fetch(), validate() y get_metadata().
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class ConnectorMetadata:
    """Información descriptiva sobre un conector."""
    name: str
    description: str
    base_url: str
    granularity: str          # 'hourly' | 'daily' | 'monthly'
    auth_required: bool = False
    notes: str = ""


class BaseConnector(ABC):
    """
    Interfaz base para todos los conectores de fuentes de datos.

    Cada conector concreto debe implementar:
    - fetch(): descargar datos crudos y retornarlos como DataFrame
    - validate(): verificar que el DataFrame tiene la estructura esperada
    - get_metadata(): describir la fuente

    El pipeline principal llama a fetch() → validate() → retorna DataFrame.
    Si fetch() falla, debe lanzar ConnectorError con un mensaje descriptivo.
    """

    @abstractmethod
    def fetch(self, date_from: date, date_to: date) -> pd.DataFrame:
        """
        Descarga datos en el rango de fechas indicado.

        Args:
            date_from: fecha de inicio (inclusive)
            date_to:   fecha de fin (inclusive)

        Returns:
            DataFrame con los datos crudos (sin limpiar).

        Raises:
            ConnectorError: si la descarga falla por cualquier motivo.
        """

    @abstractmethod
    def validate(self, df: pd.DataFrame) -> bool:
        """
        Verifica que el DataFrame tenga las columnas y tipos mínimos esperados.

        Returns:
            True si el DataFrame es válido, False en caso contrario.
        """

    @abstractmethod
    def get_metadata(self) -> ConnectorMetadata:
        """Retorna metadatos descriptivos de esta fuente."""


class ConnectorError(Exception):
    """Error genérico de conector. Incluye la fuente y el motivo del fallo."""

    def __init__(self, source: str, message: str, original: Exception | None = None):
        self.source = source
        self.original = original
        super().__init__(f"[{source}] {message}")

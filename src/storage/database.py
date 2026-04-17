"""
database.py — Conexión y creación del engine SQLAlchemy.

Centraliza la gestión del engine para que sea fácil cambiar de SQLite
a PostgreSQL en el futuro (solo hay que modificar get_engine()).
"""

import logging
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

from src.storage.models import metadata

logger = logging.getLogger(__name__)


def get_engine(db_path: Path) -> Engine:
    """
    Crea y retorna un engine SQLAlchemy apuntando a la DB indicada.

    Trade-off SQLite vs persistencia en Streamlit Cloud
    ────────────────────────────────────────────────────
    El filesystem de Streamlit Cloud es efímero: los archivos escritos
    durante una sesión se pierden al reiniciar el servidor.

    Para este proyecto eso es ACEPTABLE porque:
    - Todos los datos provienen de fuentes públicas (ADME, UTE) y son
      re-descargables en cualquier momento.
    - La DB actúa como cache intra-sesión: si el usuario ejecuta el
      pipeline varias veces en la misma sesión, los datos ya descargados
      no se vuelven a descargar (INSERT OR IGNORE).
    - No hay datos generados por el usuario ni lógica que dependa de
      historial persistente entre sesiones.

    Si en el futuro se necesita persistencia real (ej. caché entre
    sesiones, múltiples usuarios compartiendo datos ya procesados),
    migrar a PostgreSQL cambiando la URL aquí:
        postgresql+psycopg2://user:pass@host:5432/energy_uy

    La ruta por defecto en producción (Streamlit Cloud) apunta a
    /tmp/energy_uy.sqlite, configurable via secrets DB_PATH.
    """
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, echo=False)

    # Habilitar foreign keys en SQLite (desactivado por defecto)
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    logger.debug("Engine creado: %s", url)
    return engine


def init_db(engine: Engine) -> None:
    """
    Crea todas las tablas definidas en models.py si no existen.
    Es seguro ejecutar múltiples veces (usa CREATE TABLE IF NOT EXISTS).
    """
    metadata.create_all(engine)
    logger.info("Base de datos inicializada correctamente.")

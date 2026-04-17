"""
models.py — Definición del esquema de la base de datos.

Usa SQLAlchemy Core (sin ORM) para mantener compatibilidad con SQLite y
permitir migración futura a PostgreSQL cambiando únicamente el engine.
"""

from sqlalchemy import (
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    text,
)

metadata = MetaData()

# ─── Generación horaria (ADME SCADA) ─────────────────────────────────────────

generation_hourly = Table(
    "generation_hourly",
    metadata,
    Column("id",          Integer, primary_key=True, autoincrement=True),
    Column("timestamp",   String,  nullable=False),   # ISO8601: '2024-01-15T14:00:00'
    Column("source",      String,  nullable=False),   # wind | solar | thermal | biomass | hydro
    Column("source_type", String,  nullable=False),   # renewable | non_renewable | external
    Column("plant_name",  String,  nullable=True),    # nombre de central (puede ser None)
    Column("value_mw",    Float,   nullable=False),
    Column("data_source", String,  nullable=False),   # 'adme_scada'
    Column("created_at",  String,  server_default=text("(datetime('now'))")),
    UniqueConstraint("timestamp", "source", "plant_name", "data_source", name="uq_gen_hourly"),
)

# ─── Generación diaria (UTE Bajadas) ─────────────────────────────────────────

generation_daily = Table(
    "generation_daily",
    metadata,
    Column("id",          Integer, primary_key=True, autoincrement=True),
    Column("date",        String,  nullable=False),   # ISO8601: '2024-01-15'
    Column("source",      String,  nullable=False),
    Column("source_type", String,  nullable=False),
    Column("value_mwh",   Float,   nullable=False),
    Column("data_source", String,  nullable=False),   # 'ute_bajadas'
    Column("created_at",  String,  server_default=text("(datetime('now'))")),
    UniqueConstraint("date", "source", "data_source", name="uq_gen_daily"),
)

# ─── Demanda diaria ───────────────────────────────────────────────────────────

demand_daily = Table(
    "demand_daily",
    metadata,
    Column("id",          Integer, primary_key=True, autoincrement=True),
    Column("date",        String,  nullable=False),
    Column("value_mwh",   Float,   nullable=True),
    Column("min_mw",      Float,   nullable=True),
    Column("max_mw",      Float,   nullable=True),
    Column("data_source", String,  nullable=False),
    Column("created_at",  String,  server_default=text("(datetime('now'))")),
    UniqueConstraint("date", "data_source", name="uq_demand_daily"),
)

# ─── Intercambios internacionales ─────────────────────────────────────────────

exchange = Table(
    "exchange",
    metadata,
    Column("id",          Integer, primary_key=True, autoincrement=True),
    Column("timestamp",   String,  nullable=False),   # fecha o fecha+hora
    Column("granularity", String,  nullable=False),   # 'hourly' | 'daily'
    Column("country",     String,  nullable=False),   # 'argentina' | 'brasil'
    Column("direction",   String,  nullable=False),   # 'import' | 'export'
    Column("value_mw",    Float,   nullable=True),    # MW (horario)
    Column("value_mwh",   Float,   nullable=True),    # MWh (diario)
    Column("data_source", String,  nullable=False),
    Column("created_at",  String,  server_default=text("(datetime('now'))")),
    UniqueConstraint("timestamp", "granularity", "country", "direction", "data_source", name="uq_exchange"),
)

# ─── Precios spot (ADME Control Panel) ───────────────────────────────────────

spot_price = Table(
    "spot_price",
    metadata,
    Column("id",          Integer, primary_key=True, autoincrement=True),
    Column("timestamp",   String,  nullable=False),
    Column("granularity", String,  nullable=False),   # 'hourly' | 'daily'
    Column("price_usd",   Float,   nullable=True),
    Column("price_uyu",   Float,   nullable=True),
    Column("data_source", String,  nullable=False),   # 'adme_precio_spot'
    Column("created_at",  String,  server_default=text("(datetime('now'))")),
    UniqueConstraint("timestamp", "granularity", "data_source", name="uq_spot_price"),
)

# ─── Log de ingestas ─────────────────────────────────────────────────────────

ingestion_log = Table(
    "ingestion_log",
    metadata,
    Column("id",               Integer, primary_key=True, autoincrement=True),
    Column("run_at",           String,  nullable=False),
    Column("source_name",      String,  nullable=False),
    Column("dataset",          String,  nullable=False),
    Column("date_from",        String,  nullable=True),
    Column("date_to",          String,  nullable=True),
    Column("records_fetched",  Integer, nullable=True),
    Column("records_inserted", Integer, nullable=True),
    Column("status",           String,  nullable=False),  # success | error | partial
    Column("error_message",    String,  nullable=True),
    Column("duration_sec",     Float,   nullable=True),
)

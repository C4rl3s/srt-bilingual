"""Capa de acceso a datos: engine, sesión y base declarativa de SQLAlchemy.

Usa SQLAlchemy 2.0 en modo **síncrono** (suficiente y más simple para una app de
un solo usuario sobre SQLite). Las tablas NO se crean aquí con `create_all()`; su
esquema lo gestiona Alembic (ver `backend/alembic/`).
"""

from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# `check_same_thread=False` permite que la conexión SQLite se use desde el pool de
# hilos de FastAPI sin avisos; al ser un solo usuario no hay riesgo de concurrencia.
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base declarativa común a todos los modelos ORM."""


@event.listens_for(Engine, "connect")
def _activar_foreign_keys(dbapi_connection, connection_record) -> None:
    """SQLite ignora las claves foráneas por defecto; las activamos en cada conexión
    para que el borrado en cascada (carpeta → subtítulos) funcione de verdad."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_db() -> Generator[Session]:
    """Dependencia de FastAPI: entrega una sesión y la cierra al terminar."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

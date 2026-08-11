"""Fixtures compartidas de los tests.

Cada test corre contra una base de datos SQLite **temporal y nueva** (fichero en
`tmp_path`), independiente de la de desarrollo. El esquema se crea con
`create_all()` en vez de con Alembic: en runtime manda Alembic, pero en los tests
interesa un arranque rápido a partir de los mismos modelos.
"""

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401 — registra las tablas en Base.metadata
from app.db import Base, get_db
from app.main import app as fastapi_app
from app.models.library_folder import CarpetaBiblioteca

# Contenido SRT válido reutilizado por varios tests: 2 bloques y 18 caracteres de
# texto ("Hola, mundo." = 12 + "Adiós." = 6), sin contar índices ni marcas de tiempo.
SRT_EJEMPLO = """1
00:00:01,000 --> 00:00:03,000
Hola, mundo.

2
00:00:04,000 --> 00:00:06,500
Adiós.
"""


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    """Engine SQLite sobre un fichero temporal, con el esquema ya creado."""
    motor = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(motor)
    yield motor
    motor.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """Sesión de base de datos contra la BD temporal."""
    sesion_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    sesion = sesion_local()
    try:
        yield sesion
    finally:
        sesion.close()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    """Cliente HTTP de la API con `get_db` apuntando a la sesión de test."""
    fastapi_app.dependency_overrides[get_db] = lambda: db
    with TestClient(fastapi_app) as cliente:
        yield cliente
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def registrar_carpetas(db: Session) -> Callable[..., list[CarpetaBiblioteca]]:
    """Da de alta carpetas en la base de datos, como haría `POST /folders`.

    No resuelve las rutas a propósito: las guarda tal cual se las pasan, para que
    los tests puedan comparar contra las rutas que ellos mismos construyen.
    """

    def _registrar(*rutas: Path | str, activa: bool = True) -> list[CarpetaBiblioteca]:
        carpetas = [CarpetaBiblioteca(ruta=str(ruta), activa=activa) for ruta in rutas]
        db.add_all(carpetas)
        db.commit()
        return carpetas

    return _registrar


def escribir_srt(destino: Path, contenido: str = SRT_EJEMPLO) -> Path:
    """Crea un `.srt` de prueba en `destino` y devuelve su ruta."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(contenido, encoding="utf-8")
    return destino

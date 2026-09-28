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
from app.models.enums import Idioma
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


class TraductorFalso:
    """Proveedor de pega que cumple el `Protocol` `Translator` sin heredar de él.

    Ningún test llama a DeepL: esto devuelve cada texto marcado y apunta las
    llamadas, para que los tests comprueben qué se envió.
    """

    nombre = "falso"

    def __init__(self) -> None:
        self.llamadas: list[tuple[list[str], Idioma, Idioma]] = []

    def traducir(self, textos: list[str], origen: Idioma, destino: Idioma) -> list[str]:
        self.llamadas.append((list(textos), origen, destino))
        return [f"[{destino.value}] {texto}" for texto in textos]


def srt_completo(num_bloques: int = 120, texto: str = "Hola, mundo.") -> str:
    """Contenido `.srt` del tamaño de un subtítulo real.

    `SRT_EJEMPLO` tiene 2 bloques, y la selección de origen descarta por forzado
    encubierto lo que baja de 100 (`seleccion.MIN_BLOQUES`). Los tests que necesitan
    un origen válido usan este.
    """
    bloques = []
    for i in range(num_bloques):
        inicio = f"00:{i // 30:02d}:{i % 30 * 2:02d},000"
        fin = f"00:{i // 30:02d}:{i % 30 * 2:02d},900"
        bloques.append(f"{i + 1}\n{inicio} --> {fin}\n{texto}\n")
    return "\n".join(bloques)


def escribir_srt(destino: Path, contenido: str = SRT_EJEMPLO) -> Path:
    """Crea un `.srt` de prueba en `destino` y devuelve su ruta."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(contenido, encoding="utf-8")
    return destino


def escribir_video(destino: Path, contenido: bytes = b"\x1a\x45\xdf\xa3 mkv de mentira") -> Path:
    """Crea un fichero de vídeo de pega. El escaneo no lo abre: solo lo inventaría."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(contenido)
    return destino

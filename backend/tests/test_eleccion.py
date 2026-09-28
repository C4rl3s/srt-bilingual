"""Tests de la elección automática de proveedor según su cupo."""

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.translate import get_fabrica_sesion, get_fabrica_traductor
from app.config import settings
from app.main import app as fastapi_app
from app.models.library_folder import CarpetaBiblioteca
from app.models.subtitle_file import ArchivoSubtitulo
from app.services.scanner import escanear
from app.services.translation.base import Consumo, CuotaAgotada
from app.services.translation.consumo import EstadoCupo, FuenteCupo
from app.services.translation.eleccion import Asignador
from tests.conftest import TraductorFalso, escribir_srt, escribir_video, srt_completo

Registrar = Callable[..., list[CarpetaBiblioteca]]


def _estado(proveedor: str, libre: int | None, disponible: bool = True) -> EstadoCupo:
    limite = None if libre is None else libre
    return EstadoCupo(
        proveedor,
        disponible,
        None if disponible else "Falta la clave",
        FuenteCupo.REGISTRO,
        0,
        0,
        limite,
    )


def test_elige_el_primero_con_cupo_en_orden_de_preferencia() -> None:
    asignador = Asignador([_estado("azure", 2_000_000), _estado("deepl", 1_000_000)])

    assert asignador.asignar(50_000) == "azure"


def test_salta_al_siguiente_si_no_cabe() -> None:
    asignador = Asignador([_estado("azure", 30_000), _estado("deepl", 1_000_000)])

    assert asignador.asignar(50_000) == "deepl"


def test_pide_un_margen_sobre_lo_previsto() -> None:
    """Justo lo previsto no basta: cada proveedor cuenta a su manera."""
    asignador = Asignador([_estado("azure", 50_000), _estado("deepl", 1_000_000)])

    assert asignador.asignar(50_000) == "deepl"


def test_las_reservas_de_la_misma_peticion_cuentan() -> None:
    """Dos películas que caben por separado en Azure, pero no juntas."""
    asignador = Asignador([_estado("azure", 100_000), _estado("deepl", 1_000_000)])

    assert [asignador.asignar(60_000), asignador.asignar(60_000)] == ["azure", "deepl"]


def test_salta_los_proveedores_no_disponibles() -> None:
    asignador = Asignador(
        [_estado("azure", 2_000_000, disponible=False), _estado("deepl", 1_000_000)]
    )

    assert asignador.asignar(50_000) == "deepl"


def test_con_limite_desconocido_se_confia_en_el_proveedor() -> None:
    """La API de DeepL no responde: se usa igual; si se agota, el reintento cambia."""
    assert Asignador([_estado("deepl", None)]).asignar(50_000) == "deepl"


def test_sin_cupo_en_ninguno_explica_por_que() -> None:
    asignador = Asignador([_estado("azure", 8_500), _estado("deepl", 12_000, disponible=False)])

    assert asignador.asignar(64_751) is None
    motivo = asignador.motivo(64_751)
    assert "64.751 caracteres" in motivo
    assert "azure: 8.500 libres" in motivo
    assert "deepl: Falta la clave" in motivo


# --- De punta a punta, por la API --------------------------------------------------------


class CupoApi(TraductorFalso):
    """Proveedor que informa de su cupo (como DeepL), con un límite a medida."""

    def __init__(self, nombre: str, usados: int, limite: int) -> None:
        super().__init__()
        self.nombre = nombre
        self._consumo = Consumo(usados=usados, limite=limite)

    def consumo(self) -> Consumo:
        return self._consumo


@pytest.fixture
def api_dos_proveedores(
    client: TestClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Callable[[dict[str, TraductorFalso]], TestClient]]:
    """Cliente con `azure,deepl` configurados y los proveedores falsos que se pasen."""
    monkeypatch.setattr(settings, "translation_providers", "azure,deepl")
    fabrica_sesion = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    fastapi_app.dependency_overrides[get_fabrica_sesion] = lambda: fabrica_sesion

    def configurar(proveedores: dict[str, TraductorFalso]) -> TestClient:
        fastapi_app.dependency_overrides[get_fabrica_traductor] = lambda: (
            lambda nombre: proveedores[nombre or "azure"]
        )
        return client

    yield configurar


def _dos_peliculas(raiz: Path, registrar: Registrar, db: Session) -> list[int]:
    """Dos películas de 120 × «Hola, mundo.» = 1440 caracteres cada una."""
    for titulo in ("Una", "Otra"):
        escribir_video(raiz / titulo / f"{titulo}.mkv")
        escribir_srt(raiz / titulo / f"{titulo}.es.srt", srt_completo())
    registrar(raiz)
    escanear(db)
    return [s.id for s in db.scalars(select(ArchivoSubtitulo).order_by(ArchivoSubtitulo.nombre))]


def test_reparte_una_peticion_entre_proveedores(
    api_dos_proveedores, db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    """Azure (preferido) tiene cupo para una película; la otra va a DeepL."""
    cliente = api_dos_proveedores(
        {"azure": CupoApi("azure", 0, 2_000), "deepl": CupoApi("deepl", 0, 1_000_000)}
    )
    ids = _dos_peliculas(tmp_path, registrar_carpetas, db)

    respuesta = cliente.post("/translate", json={"subtitulo_ids": ids}).json()

    assert respuesta["rechazados"] == []
    assert sorted(t["proveedor"] for t in respuesta["trabajos"]) == ["azure", "deepl"]


def test_sin_cupo_no_crea_el_trabajo(
    api_dos_proveedores, db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    cliente = api_dos_proveedores(
        {"azure": CupoApi("azure", 1_900, 2_000), "deepl": CupoApi("deepl", 999_000, 1_000_000)}
    )
    ids = _dos_peliculas(tmp_path, registrar_carpetas, db)

    respuesta = cliente.post("/translate", json={"subtitulo_ids": ids[:1]}).json()

    assert respuesta["trabajos"] == []
    (rechazo,) = respuesta["rechazados"]
    assert "Sin cupo suficiente para 1.440 caracteres" in rechazo["motivo"]
    assert cliente.get("/translate/jobs").json() == []


class SeAgotaAlTraducir(CupoApi):
    """Parece tener cupo, pero se agota en la segunda llamada; a partir de ahí su
    API ya informa de que está lleno."""

    def traducir(self, textos, origen, destino):
        if self.llamadas:
            self._consumo = Consumo(usados=self._consumo.limite, limite=self._consumo.limite)
            raise CuotaAgotada("Cupo agotado a mitad")
        return super().traducir(textos, origen, destino)


def test_reintentar_tras_agotarse_elige_otro_proveedor(
    api_dos_proveedores, db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    azure = SeAgotaAlTraducir("azure", 0, 1_000_000)
    cliente = api_dos_proveedores({"azure": azure, "deepl": CupoApi("deepl", 0, 1_000_000)})
    ids = _dos_peliculas(tmp_path, registrar_carpetas, db)

    (fallido,) = cliente.post("/translate", json={"subtitulo_ids": ids[:1]}).json()["trabajos"]
    assert cliente.get(f"/translate/jobs/{fallido['id']}").json()["estado"] == "FAILED"

    (reintento,) = cliente.post("/translate", json={"subtitulo_ids": ids[:1]}).json()["trabajos"]

    assert (fallido["proveedor"], reintento["proveedor"]) == ("azure", "deepl")
    assert cliente.get(f"/translate/jobs/{reintento['id']}").json()["estado"] == "DONE"

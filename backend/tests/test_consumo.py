"""Tests del consumo de cupo por proveedor (`services/translation/consumo.py`)."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.translate import get_fabrica_traductor
from app.config import Settings, settings
from app.main import app as fastapi_app
from app.models.enums import EstadoTrabajo, Idioma, ModoTrabajo
from app.models.library_folder import CarpetaBiblioteca
from app.models.subtitle_file import ArchivoSubtitulo
from app.models.translation_job import TrabajoTraduccion
from app.services import trabajos
from app.services.scanner import escanear
from app.services.translation import consumo
from app.services.translation.base import Consumo, ErrorTraduccion, ProveedorNoDisponible
from app.services.translation.consumo import FuenteCupo
from tests.conftest import (
    TraductorFalso,
    cupo_de_sobra,
    escribir_srt,
    escribir_video,
    srt_completo,
)

Registrar = Callable[..., list[CarpetaBiblioteca]]
AHORA = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


class ConApi(TraductorFalso):
    """Como DeepL: informa de su cupo."""

    nombre = "deepl"

    def consumo(self) -> Consumo:
        return Consumo(usados=61, limite=1_000_000)


class ConApiCaida(ConApi):
    def consumo(self) -> Consumo:
        raise ErrorTraduccion("sin red")


class SinApi(TraductorFalso):
    """Como Azure: no deja consultar su consumo."""

    nombre = "azure"


def _fabrica(**proveedores):
    def fabricar(nombre: str | None):
        if nombre not in proveedores:
            raise ProveedorNoDisponible(f"Falta la clave de {nombre}")
        return proveedores[nombre]()

    return fabricar


def _limites(nombre: str) -> int | None:
    return 2_000_000 if nombre == "azure" else None


def _trabajo(
    db: Session,
    proveedor: str,
    estado: EstadoTrabajo,
    enviados: int,
    previstos: int,
    creado: datetime,
) -> None:
    db.add(
        TrabajoTraduccion(
            modo=ModoTrabajo.TRADUCCION,
            estado=estado,
            ruta_origen="/pelis/x.srt",
            idioma_origen=Idioma.ES,
            proveedor=proveedor,
            num_caracteres=enviados,
            caracteres_previstos=previstos,
            creado_en=creado,
        )
    )
    db.commit()


def test_con_api_manda_lo_que_dice_el_proveedor(db: Session) -> None:
    # Un trabajo en curso con 40.000 previstos y 10.000 enviados reserva 30.000.
    _trabajo(db, "deepl", EstadoTrabajo.RUNNING, 10_000, 40_000, AHORA)

    (estado,) = consumo.estados(db, ["deepl"], _fabrica(deepl=ConApi), _limites, AHORA)

    assert estado.fuente is FuenteCupo.API
    assert (estado.usados, estado.reservados, estado.limite) == (61, 30_000, 1_000_000)
    assert estado.libre == 1_000_000 - 61 - 30_000


def test_sin_api_cuenta_el_registro_del_mes(db: Session) -> None:
    _trabajo(db, "azure", EstadoTrabajo.DONE, 30_000, 30_000, AHORA)
    _trabajo(db, "azure", EstadoTrabajo.FAILED, 5_000, 40_000, AHORA)  # lo enviado cuenta
    _trabajo(db, "azure", EstadoTrabajo.DONE, 100_000, 100_000, datetime(2026, 8, 30, tzinfo=UTC))
    _trabajo(db, "deepl", EstadoTrabajo.DONE, 70_000, 70_000, AHORA)  # otro proveedor
    _trabajo(db, "azure", EstadoTrabajo.QUEUED, 0, 20_000, AHORA)

    (estado,) = consumo.estados(db, ["azure"], _fabrica(azure=SinApi), _limites, AHORA)

    assert estado.fuente is FuenteCupo.REGISTRO
    assert estado.usados == 35_000  # ni el del mes pasado ni el de DeepL
    assert estado.reservados == 20_000
    assert estado.libre == 2_000_000 - 35_000 - 20_000


def test_un_proveedor_sin_configurar_se_informa_igual(db: Session) -> None:
    (estado,) = consumo.estados(db, ["azure"], _fabrica(), _limites, AHORA)

    assert not estado.disponible
    assert "clave" in estado.motivo


def test_si_la_api_no_responde_se_cae_al_registro(db: Session) -> None:
    _trabajo(db, "deepl", EstadoTrabajo.DONE, 5_000, 5_000, AHORA)

    (estado,) = consumo.estados(db, ["deepl"], _fabrica(deepl=ConApiCaida), _limites, AHORA)

    assert estado.fuente is FuenteCupo.REGISTRO
    assert estado.usados == 5_000
    assert estado.libre is None  # sin límite conocido


def test_el_orden_de_los_estados_es_el_de_preferencia(db: Session) -> None:
    fabrica = _fabrica(deepl=ConApi, azure=SinApi)

    nombres = [
        e.proveedor for e in consumo.estados(db, ["azure", "deepl"], fabrica, _limites, AHORA)
    ]

    assert nombres == ["azure", "deepl"]


@pytest.mark.parametrize(
    ("lista", "singular", "esperado"),
    [
        ("Azure, DeepL", "deepl", ["azure", "deepl"]),
        (None, "deepl", ["deepl"]),  # la forma de la Fase 3 sigue valiendo
    ],
)
def test_proveedores_configurados(lista: str | None, singular: str, esperado: list[str]) -> None:
    ajustes = Settings(_env_file=None, translation_providers=lista, translation_provider=singular)

    assert ajustes.proveedores == esperado


def test_una_traduccion_reserva_su_texto_y_una_fusion_nada(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    escribir_video(tmp_path / "Uno" / "Uno.mkv")
    escribir_srt(tmp_path / "Uno" / "Uno.es.srt", srt_completo())
    escribir_video(tmp_path / "Dos" / "Dos.mkv")
    escribir_srt(tmp_path / "Dos" / "Dos.es.srt", srt_completo())
    escribir_srt(tmp_path / "Dos" / "Dos.ko.srt", srt_completo(texto="안녕."))
    registrar_carpetas(tmp_path)
    escanear(db)
    ids = {s.nombre: s.id for s in db.scalars(select(ArchivoSubtitulo))}

    creados, _ = trabajos.crear(
        db, [ids["Uno.es.srt"], ids["Dos.es.srt"]], estados_cupo=cupo_de_sobra
    )

    previstos = {t.modo: t.caracteres_previstos for t in creados}
    assert previstos == {ModoTrabajo.TRADUCCION: 120 * len("Hola, mundo."), ModoTrabajo.FUSION: 0}


def test_el_endpoint_de_cupos(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "translation_providers", "azure,deepl")
    fastapi_app.dependency_overrides[get_fabrica_traductor] = lambda: _fabrica(deepl=ConApi)

    cuerpo = client.get("/translate/cupos").json()

    assert [(c["proveedor"], c["disponible"], c["fuente"]) for c in cuerpo] == [
        ("azure", False, "REGISTRO"),
        ("deepl", True, "API"),
    ]
    assert cuerpo[1]["libre"] == 1_000_000 - 61

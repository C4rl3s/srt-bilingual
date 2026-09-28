"""Tests del modelo `translation_job`."""

from collections.abc import Callable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import EstadoTrabajo, Idioma, ModoTrabajo
from app.models.library_folder import CarpetaBiblioteca
from app.models.subtitle_file import ArchivoSubtitulo
from app.models.translation_job import TrabajoTraduccion
from app.services.scanner import escanear
from tests.conftest import escribir_srt

Registrar = Callable[..., list[CarpetaBiblioteca]]


def _trabajo_de(db: Session, sub: ArchivoSubtitulo, **extra) -> TrabajoTraduccion:
    campos = {
        "modo": ModoTrabajo.TRADUCCION,
        "subtitulo_id": sub.id,
        "ruta_origen": sub.ruta,
        "idioma_origen": sub.idioma_origen,
    }
    trabajo = TrabajoTraduccion(**(campos | extra))
    db.add(trabajo)
    db.commit()
    return trabajo


def test_valores_por_defecto(db: Session, tmp_path: Path, registrar_carpetas: Registrar) -> None:
    escribir_srt(tmp_path / "Pelicula.es.srt")
    registrar_carpetas(tmp_path)
    escanear(db)
    sub = db.scalars(select(ArchivoSubtitulo)).one()

    trabajo = _trabajo_de(db, sub)

    assert trabajo.estado is EstadoTrabajo.QUEUED
    assert trabajo.activo
    assert (trabajo.num_caracteres, trabajo.bloques_procesados) == (0, 0)
    assert trabajo.creado_en is not None and trabajo.finalizado_en is None
    assert trabajo.origen is sub


def test_un_trabajo_terminado_no_esta_activo(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    escribir_srt(tmp_path / "Pelicula.es.srt")
    registrar_carpetas(tmp_path)
    escanear(db)
    sub = db.scalars(select(ArchivoSubtitulo)).one()

    trabajo = _trabajo_de(db, sub, estado=EstadoTrabajo.DONE)

    assert not trabajo.activo


def test_el_trabajo_sobrevive_a_que_desaparezca_su_subtitulo(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    """Es historial para la Fase 4: si un escaneo borra el `.srt` de origen, el
    trabajo se queda sin clave foránea pero conserva la ruta y los caracteres."""
    ruta = escribir_srt(tmp_path / "Pelicula.es.srt")
    registrar_carpetas(tmp_path)
    escanear(db)
    sub = db.scalars(select(ArchivoSubtitulo)).one()
    trabajo = _trabajo_de(db, sub, estado=EstadoTrabajo.DONE, num_caracteres=18)

    ruta.unlink()
    escanear(db)  # borra la fila huérfana
    db.expire_all()

    conservado = db.get(TrabajoTraduccion, trabajo.id)
    assert conservado is not None
    assert conservado.subtitulo_id is None
    assert conservado.ruta_origen == str(ruta)
    assert conservado.num_caracteres == 18


def test_un_trabajo_de_fusion_referencia_al_coreano(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    escribir_srt(tmp_path / "Pelicula.es.srt")
    escribir_srt(tmp_path / "Pelicula.ko.srt")
    registrar_carpetas(tmp_path)
    escanear(db)
    subs = {s.idioma_origen: s for s in db.scalars(select(ArchivoSubtitulo))}

    trabajo = _trabajo_de(
        db,
        subs[Idioma.ES],
        modo=ModoTrabajo.FUSION,
        subtitulo_coreano_id=subs[Idioma.KO].id,
        ruta_coreano=subs[Idioma.KO].ruta,
        calidad_alineacion=0.9,
    )

    assert trabajo.coreano is subs[Idioma.KO]
    assert trabajo.proveedor is None

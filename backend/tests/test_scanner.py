"""Tests del escaneo de carpetas: reconciliación disco ↔ base de datos."""

import os
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import EstadoSubtitulo, Idioma
from app.models.library_folder import CarpetaBiblioteca
from app.models.subtitle_file import ArchivoSubtitulo
from app.services.scanner import escanear
from tests.conftest import escribir_srt


def _subtitulos(db: Session) -> list[ArchivoSubtitulo]:
    return list(db.scalars(select(ArchivoSubtitulo).order_by(ArchivoSubtitulo.ruta)).all())


def test_escaneo_inicial_inventaria_los_srt(
    db: Session, tmp_path: Path, configurar_carpetas: Callable[..., None]
) -> None:
    escribir_srt(tmp_path / "Pelicula.es.srt")
    escribir_srt(tmp_path / "series" / "Cap01.es.srt")  # también los subdirectorios
    configurar_carpetas(tmp_path)

    resumen = escanear(db)

    assert resumen.carpetas == 1
    assert resumen.nuevos == 2
    assert resumen.total == 2
    subs = _subtitulos(db)
    assert [s.estado for s in subs] == [EstadoSubtitulo.PENDING] * 2
    assert all(s.idioma_origen is Idioma.ES for s in subs)
    assert all(s.num_caracteres == 18 and s.num_bloques == 2 for s in subs)


def test_segundo_escaneo_sin_cambios_no_reprocesa(
    db: Session, tmp_path: Path, configurar_carpetas: Callable[..., None]
) -> None:
    escribir_srt(tmp_path / "Pelicula.es.srt")
    configurar_carpetas(tmp_path)
    escanear(db)

    resumen = escanear(db)

    assert resumen.nuevos == 0
    assert resumen.sin_cambios == 1
    assert resumen.total == 1


def test_fichero_modificado_se_reprocesa(
    db: Session, tmp_path: Path, configurar_carpetas: Callable[..., None]
) -> None:
    ruta = escribir_srt(tmp_path / "Pelicula.es.srt")
    configurar_carpetas(tmp_path)
    escanear(db)

    # Contenido más largo y mtime distinto: cambian tamaño y fecha.
    escribir_srt(ruta, "1\n00:00:01,000 --> 00:00:03,000\nUn texto bastante más largo.\n")
    os.utime(ruta, (0, 0))

    resumen = escanear(db)

    assert resumen.actualizados == 1
    assert resumen.sin_cambios == 0
    assert _subtitulos(db)[0].num_caracteres == 28


def test_detecta_como_traducido_si_existe_el_bilingue(
    db: Session, tmp_path: Path, configurar_carpetas: Callable[..., None]
) -> None:
    escribir_srt(tmp_path / "Pelicula.es.srt")
    bilingue = escribir_srt(tmp_path / "Pelicula.ES-KO.bilingue.srt")
    configurar_carpetas(tmp_path)

    resumen = escanear(db)

    # El bilingüe no se inventaría como fuente: solo cuenta el original.
    assert resumen.total == 1
    assert resumen.traducidos == 1
    sub = _subtitulos(db)[0]
    assert sub.estado is EstadoSubtitulo.TRANSLATED
    assert sub.ruta_bilingue == str(bilingue)
    assert sub.idioma_destino is Idioma.KO


def test_vuelve_a_pendiente_si_desaparece_el_bilingue(
    db: Session, tmp_path: Path, configurar_carpetas: Callable[..., None]
) -> None:
    escribir_srt(tmp_path / "Pelicula.es.srt")
    bilingue = escribir_srt(tmp_path / "Pelicula.ES-KO.bilingue.srt")
    configurar_carpetas(tmp_path)
    escanear(db)

    bilingue.unlink()
    escanear(db)

    sub = _subtitulos(db)[0]
    assert sub.estado is EstadoSubtitulo.PENDING
    assert sub.ruta_bilingue is None
    assert sub.idioma_destino is None


def test_sin_idioma_de_origen_no_se_marca_traducido(
    db: Session, tmp_path: Path, configurar_carpetas: Callable[..., None]
) -> None:
    escribir_srt(tmp_path / "Pelicula.srt")  # sin sufijo → UNKNOWN
    configurar_carpetas(tmp_path)

    escanear(db)

    sub = _subtitulos(db)[0]
    assert sub.idioma_origen is Idioma.UNKNOWN
    assert sub.estado is EstadoSubtitulo.PENDING


def test_borra_los_huerfanos(
    db: Session, tmp_path: Path, configurar_carpetas: Callable[..., None]
) -> None:
    ruta = escribir_srt(tmp_path / "Pelicula.es.srt")
    escribir_srt(tmp_path / "Otra.es.srt")
    configurar_carpetas(tmp_path)
    escanear(db)

    ruta.unlink()
    resumen = escanear(db)

    assert resumen.huerfanos_borrados == 1
    assert [s.nombre for s in _subtitulos(db)] == ["Otra.es.srt"]


def test_quitar_una_carpeta_borra_sus_subtitulos_en_cascada(
    db: Session, tmp_path: Path, configurar_carpetas: Callable[..., None]
) -> None:
    carpeta_a = tmp_path / "a"
    carpeta_b = tmp_path / "b"
    escribir_srt(carpeta_a / "Pelicula.es.srt")
    escribir_srt(carpeta_b / "Otra.es.srt")
    configurar_carpetas(carpeta_a, carpeta_b)
    escanear(db)

    configurar_carpetas(carpeta_a)  # se deja de vigilar `b`
    resumen = escanear(db)

    assert resumen.carpetas == 1
    assert len(db.scalars(select(CarpetaBiblioteca)).all()) == 1
    assert [s.nombre for s in _subtitulos(db)] == ["Pelicula.es.srt"]


def test_fichero_malformado_queda_en_error(
    db: Session, tmp_path: Path, configurar_carpetas: Callable[..., None]
) -> None:
    escribir_srt(tmp_path / "Roto.es.srt", "esto no es un subtítulo válido")
    configurar_carpetas(tmp_path)

    resumen = escanear(db)

    assert resumen.errores == 1
    sub = _subtitulos(db)[0]
    assert sub.estado is EstadoSubtitulo.ERROR
    assert sub.mensaje_error


def test_carpeta_inexistente_no_rompe_el_escaneo(
    db: Session, tmp_path: Path, configurar_carpetas: Callable[..., None]
) -> None:
    configurar_carpetas(tmp_path / "no-existe")

    resumen = escanear(db)

    assert resumen.carpetas == 1
    assert resumen.total == 0


def test_el_escaneo_registra_la_fecha_de_ultimo_escaneo(
    db: Session, tmp_path: Path, configurar_carpetas: Callable[..., None]
) -> None:
    configurar_carpetas(tmp_path)

    escanear(db)

    carpeta = db.scalars(select(CarpetaBiblioteca)).one()
    assert carpeta.ultimo_escaneo is not None

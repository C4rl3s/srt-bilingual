"""Tests del renombrado a la nomenclatura de Plex."""

from collections.abc import Callable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.library_folder import CarpetaBiblioteca
from app.models.subtitle_file import ArchivoSubtitulo
from app.services.scanner import escanear
from app.services.subtitles import renombrado
from app.services.subtitles.renombrado import Conflicto
from tests.conftest import escribir_srt, escribir_video, srt_completo

Registrar = Callable[..., list[CarpetaBiblioteca]]

# Subtítulo inglés sin idioma en el nombre: el detector lo reconoce por el contenido.
INGLES = srt_completo(texto="What are you doing here? I don't know.")


def _pelicula(raiz: Path) -> Path:
    """Carpeta de película al estilo YTS, con su único vídeo."""
    carpeta = raiz / "Psycho (1960)"
    escribir_video(carpeta / "Psycho.1960.1080p.BrRip.x264.YIFY.mp4")
    return carpeta


def _nombres(propuestas) -> list[tuple[str, str]]:
    return [(p.ruta_actual.name, p.ruta_nueva.name) for p in propuestas]


def test_propone_el_nombre_plex_para_un_srt_sin_idioma(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    carpeta = _pelicula(tmp_path)
    escribir_srt(carpeta / "Psycho.1960.1080p.BrRip.x264.YIFY.srt", INGLES)
    registrar_carpetas(tmp_path)
    escanear(db)

    propuestas = renombrado.proponer(db)

    assert _nombres(propuestas) == [
        ("Psycho.1960.1080p.BrRip.x264.YIFY.srt", "Psycho.1960.1080p.BrRip.x264.YIFY.eng.srt")
    ]
    assert propuestas[0].conflicto is None


def test_la_base_es_la_del_video_no_la_del_subtitulo(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    """*Jojo Rabbit*: `Jojo Rabbit.srt` pasa a llamarse como el vídeo."""
    carpeta = _pelicula(tmp_path)
    escribir_srt(carpeta / "Psycho.srt", INGLES)
    registrar_carpetas(tmp_path)
    escanear(db)

    (propuesta,) = renombrado.proponer(db)

    assert propuesta.ruta_nueva.name == "Psycho.1960.1080p.BrRip.x264.YIFY.eng.srt"


def test_conserva_los_flags(db: Session, tmp_path: Path, registrar_carpetas: Registrar) -> None:
    carpeta = _pelicula(tmp_path)
    escribir_srt(carpeta / "Psycho.sdh.srt", INGLES)
    registrar_carpetas(tmp_path)
    escanear(db)

    (propuesta,) = renombrado.proponer(db)

    assert propuesta.ruta_nueva.name == "Psycho.1960.1080p.BrRip.x264.YIFY.eng.sdh.srt"


def test_un_forzado_encubierto_se_nombra_como_forzado(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    """*Bugonia*: un `.srt` sin idioma de 25 bloques junto al inglés completo. Sin
    `.forced`, Plex lo ofrecería como el subtítulo inglés."""
    carpeta = _pelicula(tmp_path)
    escribir_srt(
        carpeta / "Psycho.en.srt", srt_completo(300, "What are you doing here? I don't know.")
    )
    escribir_srt(carpeta / "Psycho.srt", srt_completo(60, "What are you doing here? I don't know."))
    registrar_carpetas(tmp_path)
    escanear(db)

    (propuesta,) = renombrado.proponer(db)

    assert propuesta.ruta_nueva.name == "Psycho.1960.1080p.BrRip.x264.YIFY.eng.forced.srt"


def test_corrige_un_nombre_que_miente(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    carpeta = _pelicula(tmp_path)
    escribir_srt(carpeta / "Psycho.spa.srt", INGLES)
    registrar_carpetas(tmp_path)
    escanear(db)

    (propuesta,) = renombrado.proponer(db)

    assert propuesta.ruta_nueva.name == "Psycho.1960.1080p.BrRip.x264.YIFY.eng.srt"


def test_no_toca_un_nombre_que_ya_declara_bien_el_idioma(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    carpeta = _pelicula(tmp_path)
    escribir_srt(carpeta / "Psycho.en.srt", INGLES)  # no es `eng`, pero es correcto
    registrar_carpetas(tmp_path)
    escanear(db)

    assert renombrado.proponer(db) == []


def test_no_toca_los_de_la_carpeta_subs(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    carpeta = _pelicula(tmp_path)
    escribir_srt(carpeta / "Subs" / "Dialogo.srt", INGLES)
    registrar_carpetas(tmp_path)
    escanear(db)

    assert renombrado.proponer(db) == []


def test_no_toca_carpetas_con_varios_videos(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    carpeta = _pelicula(tmp_path)
    escribir_video(carpeta / "Psycho.1960.720p.mkv")
    escribir_srt(carpeta / "Psycho.srt", INGLES)
    registrar_carpetas(tmp_path)
    escanear(db)

    assert renombrado.proponer(db) == []


def test_marca_conflicto_si_el_nombre_ya_existe(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    carpeta = _pelicula(tmp_path)
    escribir_srt(carpeta / "Psycho.1960.1080p.BrRip.x264.YIFY.eng.srt", INGLES)
    escribir_srt(carpeta / "Psycho.1960.1080p.BrRip.x264.YIFY.srt", INGLES)
    registrar_carpetas(tmp_path)
    escanear(db)

    (propuesta,) = renombrado.proponer(db)

    assert propuesta.conflicto is Conflicto.EXISTE


def test_marca_duplicado_si_dos_quieren_el_mismo_nombre(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    """El más completo se queda el nombre; el otro no se renombra."""
    carpeta = _pelicula(tmp_path)
    escribir_srt(
        carpeta / "Completo.srt", srt_completo(200, "What are you doing here? I don't know.")
    )
    escribir_srt(carpeta / "Corto.srt", INGLES)
    registrar_carpetas(tmp_path)
    escanear(db)

    propuestas = {p.ruta_actual.name: p for p in renombrado.proponer(db)}

    assert propuestas["Completo.srt"].conflicto is None
    assert propuestas["Corto.srt"].conflicto is Conflicto.DUPLICADO


def test_aplicar_renombra_en_disco_y_en_la_base_de_datos(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    carpeta = _pelicula(tmp_path)
    original = escribir_srt(carpeta / "Psycho.srt", INGLES)
    registrar_carpetas(tmp_path)
    escanear(db)
    (propuesta,) = renombrado.proponer(db)

    resultado = renombrado.aplicar(db, [propuesta.subtitulo_id])

    nuevo = carpeta / "Psycho.1960.1080p.BrRip.x264.YIFY.eng.srt"
    assert _nombres(resultado.renombrados) == [("Psycho.srt", nuevo.name)]
    assert not original.exists() and nuevo.exists()
    sub = db.scalars(select(ArchivoSubtitulo)).one()
    assert (sub.ruta, sub.nombre) == (str(nuevo), nuevo.name)
    # El siguiente escaneo lo encuentra donde la fila dice: ni huérfano ni reparseo.
    resumen = escanear(db)
    assert (resumen.sin_cambios, resumen.nuevos, resumen.huerfanos_borrados) == (1, 0, 0)


def test_aplicar_nunca_sobrescribe(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    """Si el destino aparece entre la propuesta y la confirmación, no se toca nada."""
    carpeta = _pelicula(tmp_path)
    original = escribir_srt(carpeta / "Psycho.srt", INGLES)
    registrar_carpetas(tmp_path)
    escanear(db)
    (propuesta,) = renombrado.proponer(db)
    intruso = escribir_srt(propuesta.ruta_nueva, "contenido que no se debe perder")

    resultado = renombrado.aplicar(db, [propuesta.subtitulo_id])

    assert resultado.renombrados == []
    assert [p.conflicto for p in resultado.rechazados] == [Conflicto.EXISTE]
    assert original.exists()
    assert intruso.read_text(encoding="utf-8") == "contenido que no se debe perder"


def test_aplicar_ignora_lo_que_no_tiene_propuesta(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    carpeta = _pelicula(tmp_path)
    bien = escribir_srt(carpeta / "Psycho.en.srt", INGLES)
    registrar_carpetas(tmp_path)
    escanear(db)
    sub = db.scalars(select(ArchivoSubtitulo)).one()

    resultado = renombrado.aplicar(db, [sub.id, 9999])

    assert resultado.renombrados == [] and resultado.rechazados == []
    assert bien.exists()

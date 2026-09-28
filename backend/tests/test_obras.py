"""Tests de la agrupación de ficheros en obras (`services/obras.py`)."""

from pathlib import Path

from app.models.media_file import ArchivoMedia
from app.models.subtitle_file import ArchivoSubtitulo
from app.services.obras import agrupar_en_obras
from app.services.subtitles.naming import base_sin_idioma

RAIZ = Path("/pelis")


def _video(relativa: str) -> ArchivoMedia:
    ruta = RAIZ / relativa
    return ArchivoMedia(ruta=str(ruta), nombre=ruta.name, base=base_sin_idioma(ruta))


def _sub(relativa: str) -> ArchivoSubtitulo:
    ruta = RAIZ / relativa
    return ArchivoSubtitulo(ruta=str(ruta), nombre=ruta.name)


def _resumen(obras) -> dict[tuple[str, str], list[str]]:
    """{(carpeta, obra): [subtítulos]}, para comparar sin depender del orden."""
    return {
        (obra.directorio.name, obra.nombre): sorted(sub.nombre for sub in obra.subtitulos)
        for obra in obras
    }


def test_la_carpeta_subs_es_transparente() -> None:
    """Los `.srt` de `Subs\\` son de la película de la carpeta padre."""
    obras = agrupar_en_obras(
        [_video("Mercy (2026)/Mercy.2026.1080p.mp4")],
        [
            _sub("Mercy (2026)/Mercy.2026.1080p.spa.srt"),
            _sub("Mercy (2026)/Subs/Latin American.spa.srt"),
            _sub("Mercy (2026)/Subs/English.srt"),
        ],
    )

    assert _resumen(obras) == {
        ("Mercy (2026)", "Mercy.2026.1080p"): [
            "English.srt",
            "Latin American.spa.srt",
            "Mercy.2026.1080p.spa.srt",
        ]
    }


def test_en_una_carpeta_con_un_solo_video_todo_es_suyo() -> None:
    """*Jojo Rabbit*: `Jojo Rabbit.srt` no comparte base con el vídeo, pero no hay
    duda de a qué película pertenece."""
    obras = agrupar_en_obras(
        [_video("Jojo Rabbit (2019)/Jojo.Rabbit.2019.1080p.mp4")],
        [_sub("Jojo Rabbit (2019)/Jojo Rabbit.srt"), _sub("Jojo Rabbit (2019)/spa.srt")],
    )

    assert _resumen(obras) == {
        ("Jojo Rabbit (2019)", "Jojo.Rabbit.2019.1080p"): ["Jojo Rabbit.srt", "spa.srt"]
    }


def test_con_varios_videos_se_empareja_por_nombre() -> None:
    """Una temporada: cada subtítulo con su capítulo, sin mezclarlos."""
    obras = agrupar_en_obras(
        [_video("Serie/S01E01.mkv"), _video("Serie/S01E02.mkv")],
        [_sub("Serie/S01E01.es.srt"), _sub("Serie/S01E02.en.forced.srt")],
    )

    assert _resumen(obras) == {
        ("Serie", "S01E01"): ["S01E01.es.srt"],
        ("Serie", "S01E02"): ["S01E02.en.forced.srt"],
    }


def test_con_varios_videos_un_subtitulo_sin_pareja_forma_su_propia_obra() -> None:
    """*Perfect Days* trae dos copias del vídeo: no se adivina de cuál es `Subs\\`."""
    obras = agrupar_en_obras(
        [
            _video("Perfect Days/Perfect.Days.YTS.mp4"),
            _video("Perfect Days/Perfect.Days.BDRip.mkv"),
        ],
        [_sub("Perfect Days/Subs/Dialogue.eng.srt")],
    )

    assert _resumen(obras)[("Perfect Days", "Dialogue")] == ["Dialogue.eng.srt"]


def test_un_video_sin_subtitulos_es_una_obra_vacia() -> None:
    (obra,) = agrupar_en_obras([_video("Anime/Gunbuster - 01.mkv")], [])

    assert obra.nombre == "Gunbuster - 01"
    assert obra.subtitulos == []

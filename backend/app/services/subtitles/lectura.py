"""Lectura de un subtítulo como `list[Bloque]`, venga de donde venga.

Es el único punto por el que los trabajos y los candidatos leen un subtítulo: un
`.srt` se lee de su ruta; una pista incrustada, del fichero extraído en la caché
(`services/mkv/extraccion.py`), que será ASS o SRT según el códec de la pista.
"""

from pathlib import Path

from app.models.subtitle_file import ArchivoSubtitulo
from app.services.subtitles import ass_parser, srt_parser
from app.services.subtitles.modelo import Bloque

EXTENSIONES_ASS: frozenset[str] = frozenset({".ass", ".ssa"})


class PistaSinExtraer(Exception):
    """La pista aún no está en la caché: hay que extraerla del vídeo antes de leerla."""


def leer_fichero(ruta: Path) -> list[Bloque]:
    """Parsea un fichero de subtítulos según su extensión (ASS o SRT)."""
    if ruta.suffix.lower() in EXTENSIONES_ASS:
        return ass_parser.parsear(ruta)
    return srt_parser.parsear(ruta)


def leer_bloques(sub: ArchivoSubtitulo) -> list[Bloque]:
    """Los bloques de un subtítulo. Lanza `PistaSinExtraer` si es una pista que aún no
    se ha extraído (o cuya extracción ya no está en la caché)."""
    if not sub.es_pista:
        return srt_parser.parsear(Path(sub.ruta))
    if not esta_extraida(sub):
        raise PistaSinExtraer(f"{sub.nombre} aún no se ha extraído del vídeo")
    return leer_fichero(Path(sub.ruta_extraida))


def esta_extraida(sub: ArchivoSubtitulo) -> bool:
    """Si una pista tiene su extracción en la caché (un `.srt` siempre se puede leer)."""
    if not sub.es_pista:
        return True
    return sub.ruta_extraida is not None and Path(sub.ruta_extraida).is_file()

"""Agrupación de los ficheros inventariados en **obras** (capítulo o película).

La obra no tiene tabla propia: se deduce de las rutas, igual que el árbol. Es la
unidad con la que trabajan el árbol (una hoja por obra) y la selección del subtítulo
de origen (se elige uno por obra).

Reglas, en este orden:

1. Una subcarpeta de subtítulos (`Subs\\`) es **transparente**: sus ficheros
   pertenecen a la carpeta padre. En la biblioteca real 461 de 686 `.srt` viven ahí,
   con nombres como `English.srt` que no citan la obra.
2. Un subtítulo va con el vídeo de su carpeta que tenga su misma base
   (`Pelicula.es.srt` ↔ `Pelicula.mkv`).
3. Si no casa con ninguno pero la carpeta tiene **un único vídeo**, es de ese vídeo:
   es la carpeta de una película, y todo lo que hay dentro es suyo (`spa.srt`,
   `Jojo Rabbit.srt` junto a `Jojo.Rabbit.2019.1080p….mp4`).
4. Si no, forma obra con los subtítulos de su misma base (carpetas de series con
   varios capítulos, o subtítulos sin vídeo).
"""

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from app.models.media_file import ArchivoMedia
from app.models.subtitle_file import ArchivoSubtitulo
from app.services.subtitles.naming import base_sin_idioma

# Nombres de subcarpeta que se consideran contenedores de subtítulos de la obra.
CARPETAS_SUBTITULOS: frozenset[str] = frozenset({"subs", "subtitles", "subtitulos"})


@dataclass
class Obra:
    """Un capítulo o película: su carpeta, su nombre y sus ficheros."""

    directorio: Path
    nombre: str
    videos: list[ArchivoMedia] = field(default_factory=list)
    subtitulos: list[ArchivoSubtitulo] = field(default_factory=list)


def directorio_de_obra(ruta: Path) -> Path:
    """Carpeta a la que pertenece el fichero, saltando la subcarpeta `Subs\\`."""
    padre = ruta.parent
    if padre.name.lower() in CARPETAS_SUBTITULOS:
        return padre.parent
    return padre


def agrupar_en_obras(videos: list[ArchivoMedia], subtitulos: list[ArchivoSubtitulo]) -> list[Obra]:
    """Reparte vídeos y subtítulos en obras según las reglas del módulo."""
    obras: dict[tuple[Path, str], Obra] = {}
    videos_por_directorio: dict[Path, list[ArchivoMedia]] = defaultdict(list)

    def obra(directorio: Path, nombre: str) -> Obra:
        return obras.setdefault((directorio, nombre), Obra(directorio, nombre))

    for video in videos:
        directorio = directorio_de_obra(Path(video.ruta))
        obra(directorio, video.base).videos.append(video)
        videos_por_directorio[directorio].append(video)

    for sub in subtitulos:
        directorio = directorio_de_obra(Path(sub.ruta))
        base = base_sin_idioma(Path(sub.nombre))
        videos_del_directorio = videos_por_directorio.get(directorio, [])
        if (directorio, base) in obras:
            nombre = base
        elif len(videos_del_directorio) == 1:
            nombre = videos_del_directorio[0].base
        else:
            nombre = base
        obra(directorio, nombre).subtitulos.append(sub)

    return list(obras.values())

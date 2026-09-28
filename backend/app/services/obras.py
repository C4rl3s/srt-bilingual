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

from app.config import settings
from app.models.enums import Idioma
from app.models.media_file import ArchivoMedia
from app.models.subtitle_file import ArchivoSubtitulo
from app.services.subtitles.naming import base_sin_idioma, ruta_bilingue_de_obra

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


def obra_de(subtitulo: ArchivoSubtitulo) -> Obra:
    """La obra a la que pertenece un subtítulo, con todos sus hermanos.

    Reagrupa la carpeta entera: la obra no se guarda en ninguna tabla. Para una
    biblioteca doméstica es instantáneo (0,03 s el árbol completo de `Pelis`).
    """
    carpeta = subtitulo.carpeta
    for obra in agrupar_en_obras(list(carpeta.videos), list(carpeta.subtitulos)):
        if any(sub.id == subtitulo.id for sub in obra.subtitulos):
            return obra
    # No puede pasar: el subtítulo pertenece a su carpeta.
    raise LookupError(f"Subtítulo {subtitulo.id} sin obra")


def ruta_bilingue(obra: Obra, raiz: Path, origen: Idioma, destino: Idioma = Idioma.KO) -> Path:
    """Dónde va (o dónde se busca) el bilingüe de una obra.

    Por defecto, junto al vídeo y con su nombre. Si `OUTPUT_DIR` está configurado
    (red de seguridad para recursos de solo lectura), va allí replicando la ruta
    relativa a la carpeta vigilada `raiz`. Es la única fuente de esta regla: la usan
    el escáner, para detectar lo ya generado, y los trabajos, para escribirlo.
    """
    junto_al_video = ruta_bilingue_de_obra(obra.directorio, obra.nombre, origen, destino)
    if not settings.output_dir:
        return junto_al_video
    try:
        relativa = junto_al_video.relative_to(raiz)
    except ValueError:
        relativa = Path(junto_al_video.name)
    return Path(settings.output_dir) / relativa

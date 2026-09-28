"""Renombrado de subtítulos a la nomenclatura de Plex.

Plex asocia un subtítulo externo a su vídeo por el nombre:
`<nombre del vídeo>.<idioma>[.forced][.sdh].srt`. Un `Pelicula.srt` sin idioma, como
los de YTS, aparece en Plex como idioma desconocido. Cuando la app ha deducido el
idioma por el contenido, puede proponer el nombre correcto, y así la biblioteca queda
bien también para Plex.

Va en **dos pasos** y nunca a espaldas del usuario: `proponer` calcula la lista
`actual → nuevo` sin tocar el disco, y `aplicar` renombra solo los que el usuario
confirme, recalculando la propuesta en ese momento (no se fía de rutas que lleguen
de fuera) y **sin sobrescribir nunca** un fichero existente.
"""

from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import CODIGOS_PLEX, EstadoSubtitulo
from app.models.library_folder import CarpetaBiblioteca
from app.models.subtitle_file import ArchivoSubtitulo
from app.services.obras import agrupar_en_obras
from app.services.subtitles.seleccion import MotivoDescarte, seleccionar
from app.services.subtitles.srt_parser import analizar_nombre


class Conflicto(str, Enum):
    """Por qué una propuesta no se puede aplicar."""

    EXISTE = "EXISTE"  # ya hay un fichero con el nombre nuevo
    DUPLICADO = "DUPLICADO"  # otro subtítulo de la misma obra quiere el mismo nombre
    ERROR_DISCO = "ERROR_DISCO"  # el sistema de ficheros rechazó el renombrado


@dataclass(frozen=True, slots=True)
class Propuesta:
    """Un renombrado propuesto: de dónde a dónde y, si lo hay, qué lo impide."""

    subtitulo_id: int
    ruta_actual: Path
    ruta_nueva: Path
    conflicto: Conflicto | None = None


@dataclass
class ResultadoRenombrado:
    renombrados: list[Propuesta]
    rechazados: list[Propuesta]


def proponer(db: Session, carpeta_ids: list[int] | None = None) -> list[Propuesta]:
    """Calcula las propuestas de renombrado, sin tocar el disco."""
    consulta = select(CarpetaBiblioteca).order_by(CarpetaBiblioteca.ruta)
    if carpeta_ids is not None:
        consulta = consulta.where(CarpetaBiblioteca.id.in_(carpeta_ids))

    propuestas: list[Propuesta] = []
    for carpeta in db.scalars(consulta).all():
        for obra in agrupar_en_obras(list(carpeta.videos), list(carpeta.subtitulos)):
            # Con cero o varios vídeos no hay un nombre base inequívoco.
            if len(obra.videos) != 1:
                continue
            video = Path(obra.videos[0].ruta)
            # Los forzados encubiertos que detecta la selección se nombran como tales:
            # si no, Plex ofrecería cuatro carteles como el subtítulo inglés completo.
            encubiertos = {
                c.subtitulo.id
                for c in seleccionar(obra.subtitulos).candidatos
                if c.descarte is MotivoDescarte.POCOS_BLOQUES
            }
            reservados: set[Path] = set()
            for sub in sorted(obra.subtitulos, key=lambda s: -s.num_bloques):
                propuesta = _proponer_uno(sub, video, reservados, sub.id in encubiertos)
                if propuesta is not None:
                    propuestas.append(propuesta)
                    reservados.add(propuesta.ruta_nueva)
    return propuestas


def _proponer_uno(
    sub: ArchivoSubtitulo, video: Path, reservados: set[Path], forzado_encubierto: bool
) -> Propuesta | None:
    # Una pista incrustada no es un fichero: no hay nada que renombrar.
    if sub.es_pista:
        return None
    ruta = Path(sub.ruta)
    # Solo los que están junto al vídeo: los de `Subs\` habría que moverlos de
    # carpeta, no solo renombrarlos, y eso cambia cómo el usuario organiza la suya.
    if ruta.parent != video.parent or sub.estado is EstadoSubtitulo.ERROR:
        return None
    codigo = CODIGOS_PLEX.get(sub.idioma_origen)
    if codigo is None:
        return None
    # Si el nombre ya declara el idioma correcto, no hay nada que arreglar: se respeta
    # el nombre del usuario aunque no siga al pie de la letra la nomenclatura.
    info = analizar_nombre(sub.nombre)
    if info.idioma is sub.idioma_origen:
        return None

    forzado = info.es_forzado or forzado_encubierto
    flags = (".forced" if forzado else "") + (".sdh" if info.es_sdh else "")
    nueva = ruta.with_name(f"{video.stem}.{codigo}{flags}.srt")
    if nueva in reservados:
        conflicto = Conflicto.DUPLICADO
    elif nueva.exists():
        conflicto = Conflicto.EXISTE
    else:
        conflicto = None
    return Propuesta(sub.id, ruta, nueva, conflicto)


def aplicar(db: Session, subtitulo_ids: list[int]) -> ResultadoRenombrado:
    """Renombra en disco los subtítulos pedidos y actualiza su fila.

    Solo actúa sobre propuestas vigentes y sin conflicto; lo demás se devuelve en
    `rechazados`. El `mtime` y el tamaño no cambian al renombrar, así que el
    siguiente escaneo encuentra la fila por su ruta nueva y no la reparsea.
    """
    pedidos = set(subtitulo_ids)
    vigentes = {p.subtitulo_id: p for p in proponer(db) if p.subtitulo_id in pedidos}
    resultado = ResultadoRenombrado(renombrados=[], rechazados=[])

    for subtitulo_id in subtitulo_ids:
        propuesta = vigentes.get(subtitulo_id)
        if propuesta is None:
            continue  # ya no hay nada que renombrar (o nunca lo hubo)
        if propuesta.conflicto is not None:
            resultado.rechazados.append(propuesta)
            continue
        # Última comprobación justo antes de tocar el disco: entre la propuesta y la
        # confirmación pueden haber aparecido ficheros nuevos.
        if propuesta.ruta_nueva.exists():
            resultado.rechazados.append(replace(propuesta, conflicto=Conflicto.EXISTE))
            continue
        try:
            propuesta.ruta_actual.rename(propuesta.ruta_nueva)
        except OSError:
            # La biblioteca está en una unidad de red: un corte no debe abortar el
            # resto ni dejar la base de datos apuntando a un nombre que no existe.
            resultado.rechazados.append(replace(propuesta, conflicto=Conflicto.ERROR_DISCO))
            continue
        sub = db.get(ArchivoSubtitulo, subtitulo_id)
        sub.ruta = str(propuesta.ruta_nueva)
        sub.nombre = propuesta.ruta_nueva.name
        # Commit por fichero: el disco ya cambió, y la fila debe seguirle aunque un
        # renombrado posterior falle.
        db.commit()
        resultado.renombrados.append(propuesta)

    return resultado

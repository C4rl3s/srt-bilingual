"""Árbol de la biblioteca, derivado de las rutas ya inventariadas.

No hay ninguna tabla de jerarquía: la estructura se reconstruye partiendo la ruta de
cada fichero por sus segmentos, relativa a la carpeta que lo contiene. Así el árbol
llega hasta el último nivel sin coste de esquema y se autocorrige solo cuando
renombras carpetas en disco (el siguiente escaneo reescribe las rutas).

La **hoja es la obra**, no el fichero: el vídeo de un capítulo y sus `.srt` en varios
idiomas comparten `base_sin_idioma` y se presentan agrupados, con los idiomas que hay
y si existe ya su versión bilingüe. Un capítulo sin ningún `.srt` al lado aparece
igualmente, marcado `SIN_SUBTITULOS`: es el caso de las bibliotecas donde los
subtítulos viajan dentro del MKV.
"""

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import EstadoSubtitulo, Idioma
from app.models.library_folder import CarpetaBiblioteca
from app.models.media_file import ArchivoMedia
from app.models.subtitle_file import ArchivoSubtitulo
from app.schemas.tree import EstadoObra, NodoArbol
from app.services.subtitles.naming import base_sin_idioma


@dataclass
class _Obra:
    """Los ficheros de un mismo capítulo o película, antes de volcarlos a la hoja."""

    videos: list[ArchivoMedia] = field(default_factory=list)
    subtitulos: list[ArchivoSubtitulo] = field(default_factory=list)


@dataclass
class _Rama:
    """Nodo intermedio y mutable que se usa mientras se construye el árbol.

    Existe porque `NodoArbol` (Pydantic) es incómodo de ir rellenando por partes:
    aquí se acumula y al final se vuelca de una vez.
    """

    nombre: str
    ruta: str
    subramas: dict[str, "_Rama"] = field(default_factory=dict)
    obras: dict[str, _Obra] = field(default_factory=dict)


def construir_arbol(
    db: Session,
    carpeta_ids: list[int] | None = None,
    estado: EstadoSubtitulo | None = None,
) -> list[NodoArbol]:
    """Devuelve un árbol por carpeta vigilada, opcionalmente filtrado por estado."""
    consulta = select(CarpetaBiblioteca).order_by(CarpetaBiblioteca.ruta)
    if carpeta_ids is not None:
        consulta = consulta.where(CarpetaBiblioteca.id.in_(carpeta_ids))

    return [_arbol_de_carpeta(carpeta, estado) for carpeta in db.scalars(consulta).all()]


def _arbol_de_carpeta(carpeta: CarpetaBiblioteca, estado: EstadoSubtitulo | None) -> NodoArbol:
    raiz = _Rama(nombre=carpeta.ruta, ruta=carpeta.ruta)
    base = Path(carpeta.ruta)

    for sub in carpeta.subtitulos:
        if estado is not None and sub.estado != estado:
            continue
        obra = _localizar_obra(raiz, base, Path(sub.ruta), base_sin_idioma(Path(sub.nombre)))
        if obra is not None:
            obra.subtitulos.append(sub)

    # Con un filtro por estado de subtítulo, un vídeo sin `.srt` no puede cumplirlo:
    # se omite para no dejar hojas que contradigan el filtro.
    if estado is None:
        for video in carpeta.videos:
            obra = _localizar_obra(raiz, base, Path(video.ruta), video.base)
            if obra is not None:
                obra.videos.append(video)

    return _volcar(raiz)


def _localizar_obra(raiz: _Rama, base: Path, ruta: Path, clave: str) -> _Obra | None:
    """Baja por el árbol creando las ramas que falten y devuelve la obra del fichero.

    Devuelve `None` si la ruta no cuelga de la carpeta (fila heredada de una
    configuración anterior); el próximo escaneo la retirará por huérfana.
    """
    try:
        relativa = ruta.relative_to(base)
    except ValueError:
        return None

    rama = raiz
    for segmento in relativa.parts[:-1]:
        if segmento not in rama.subramas:
            rama.subramas[segmento] = _Rama(nombre=segmento, ruta=str(Path(rama.ruta) / segmento))
        rama = rama.subramas[segmento]

    return rama.obras.setdefault(clave, _Obra())


def _volcar(rama: _Rama) -> NodoArbol:
    """Convierte la rama mutable en `NodoArbol`, agregando de abajo hacia arriba."""
    hijos = [_volcar(sub) for sub in sorted(rama.subramas.values(), key=_orden)]
    hijos += [_nodo_obra(rama, nombre, obra) for nombre, obra in sorted(rama.obras.items())]

    return NodoArbol(
        nombre=rama.nombre,
        ruta=rama.ruta,
        hoja=False,
        hijos=hijos,
        num_obras=sum(hijo.num_obras for hijo in hijos),
        num_dual=sum(hijo.num_dual for hijo in hijos),
        num_errores=sum(hijo.num_errores for hijo in hijos),
        num_sin_subtitulos=sum(hijo.num_sin_subtitulos for hijo in hijos),
    )


def _nodo_obra(rama: _Rama, nombre: str, obra: _Obra) -> NodoArbol:
    """Hoja: un capítulo o película con su vídeo y sus subtítulos de origen."""
    subs = obra.subtitulos
    con_error = any(sub.estado is EstadoSubtitulo.ERROR for sub in subs)
    dual = any(sub.estado is EstadoSubtitulo.TRANSLATED for sub in subs)

    if con_error:
        estado_obra = EstadoObra.ERROR
    elif dual:
        estado_obra = EstadoObra.DUAL
    elif subs:
        estado_obra = EstadoObra.PENDIENTE
    else:
        estado_obra = EstadoObra.SIN_SUBTITULOS

    # `dict.fromkeys` desduplica conservando el orden de aparición, a diferencia de
    # `set`, que lo perdería y haría el listado inestable entre peticiones.
    idiomas: list[Idioma] = list(dict.fromkeys(sub.idioma_origen for sub in subs))

    return NodoArbol(
        nombre=nombre,
        ruta=str(Path(rama.ruta) / nombre),
        hoja=True,
        estado_obra=estado_obra,
        tiene_video=bool(obra.videos),
        num_obras=1,
        num_dual=1 if dual else 0,
        num_errores=1 if con_error else 0,
        num_sin_subtitulos=1 if estado_obra is EstadoObra.SIN_SUBTITULOS else 0,
        idiomas=idiomas,
        dual=dual,
        ruta_bilingue=next((sub.ruta_bilingue for sub in subs if sub.ruta_bilingue), None),
        num_caracteres=sum(sub.num_caracteres for sub in subs),
        subtitulo_ids=[sub.id for sub in subs],
    )


def _orden(rama: _Rama) -> str:
    """Orden alfabético insensible a mayúsculas, para que el listado sea previsible."""
    return rama.nombre.lower()

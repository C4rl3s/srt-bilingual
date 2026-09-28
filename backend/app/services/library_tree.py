"""Árbol de la biblioteca, derivado de las rutas ya inventariadas.

No hay ninguna tabla de jerarquía: la estructura se reconstruye partiendo la ruta de
cada fichero por sus segmentos, relativa a la carpeta que lo contiene. Así el árbol
llega hasta el último nivel sin coste de esquema y se autocorrige solo cuando
renombras carpetas en disco (el siguiente escaneo reescribe las rutas).

La **hoja es la obra**, no el fichero: el vídeo de un capítulo y sus `.srt` en varios
idiomas se presentan agrupados (reglas en `services/obras.py`), con los idiomas que
hay, el subtítulo de origen propuesto y si existe ya su versión bilingüe. Las pistas
incrustadas en el vídeo (Fase 5) cuentan como subtítulos de la obra. Un capítulo sin
ningún subtítulo aparece igualmente, marcado `SIN_SUBTITULOS`.
"""

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import EstadoSubtitulo, Idioma
from app.models.library_folder import CarpetaBiblioteca
from app.schemas.tree import EstadoObra, NodoArbol
from app.services.obras import Obra, agrupar_en_obras
from app.services.subtitles.seleccion import seleccionar
from app.services.trabajos import caracteres_previstos


@dataclass
class _Rama:
    """Nodo intermedio y mutable que se usa mientras se construye el árbol.

    Existe porque `NodoArbol` (Pydantic) es incómodo de ir rellenando por partes:
    aquí se acumula y al final se vuelca de una vez.
    """

    nombre: str
    ruta: str
    subramas: dict[str, "_Rama"] = field(default_factory=dict)
    obras: list[Obra] = field(default_factory=list)


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

    for obra in agrupar_en_obras(list(carpeta.videos), list(carpeta.subtitulos)):
        # El filtro por estado deja las obras con algún subtítulo en ese estado, pero
        # enteras: la selección del origen necesita ver todos sus subtítulos. Un vídeo
        # sin `.srt` no puede cumplir el filtro y se omite.
        if estado is not None and not any(sub.estado is estado for sub in obra.subtitulos):
            continue
        rama = _localizar_rama(raiz, base, obra.directorio)
        if rama is not None:
            rama.obras.append(obra)

    return _volcar(raiz)


def _localizar_rama(raiz: _Rama, base: Path, directorio: Path) -> _Rama | None:
    """Baja por el árbol creando las ramas que falten y devuelve la del directorio.

    Devuelve `None` si el directorio no cuelga de la carpeta (fila heredada de una
    configuración anterior); el próximo escaneo la retirará por huérfana.
    """
    try:
        relativa = directorio.relative_to(base)
    except ValueError:
        return None

    rama = raiz
    for segmento in relativa.parts:
        if segmento not in rama.subramas:
            rama.subramas[segmento] = _Rama(nombre=segmento, ruta=str(Path(rama.ruta) / segmento))
        rama = rama.subramas[segmento]
    return rama


def _volcar(rama: _Rama) -> NodoArbol:
    """Convierte la rama mutable en `NodoArbol`, agregando de abajo hacia arriba."""
    hijos = [_volcar(sub) for sub in sorted(rama.subramas.values(), key=_orden)]
    hijos += [_nodo_obra(rama, obra) for obra in sorted(rama.obras, key=lambda o: o.nombre)]

    return NodoArbol(
        nombre=rama.nombre,
        ruta=rama.ruta,
        hoja=False,
        hijos=hijos,
        num_obras=sum(hijo.num_obras for hijo in hijos),
        num_dual=sum(hijo.num_dual for hijo in hijos),
        num_errores=sum(hijo.num_errores for hijo in hijos),
        num_sin_subtitulos=sum(hijo.num_sin_subtitulos for hijo in hijos),
        num_sin_origen=sum(hijo.num_sin_origen for hijo in hijos),
    )


def _nodo_obra(rama: _Rama, obra: Obra) -> NodoArbol:
    """Hoja: un capítulo o película con su vídeo y sus subtítulos de origen."""
    subs = obra.subtitulos
    seleccion = seleccionar(subs)
    dual = any(sub.estado is EstadoSubtitulo.TRANSLATED for sub in subs)
    con_error = any(sub.estado is EstadoSubtitulo.ERROR for sub in subs)

    # Un subtítulo ilegible solo pesa si deja a la obra sin origen: si hay otro
    # válido, la obra se puede traducir igual.
    if dual:
        estado_obra = EstadoObra.DUAL
    elif not subs:
        estado_obra = EstadoObra.SIN_SUBTITULOS
    elif seleccion.elegible:
        estado_obra = EstadoObra.PENDIENTE
    elif con_error:
        estado_obra = EstadoObra.ERROR
    else:
        estado_obra = EstadoObra.SIN_ORIGEN

    # `dict.fromkeys` desduplica conservando el orden de aparición, a diferencia de
    # `set`, que lo perdería y haría el listado inestable entre peticiones.
    idiomas: list[Idioma] = list(dict.fromkeys(sub.idioma_origen for sub in subs))

    return NodoArbol(
        nombre=obra.nombre,
        ruta=str(Path(rama.ruta) / obra.nombre),
        hoja=True,
        estado_obra=estado_obra,
        tiene_video=bool(obra.videos),
        num_obras=1,
        num_dual=1 if dual else 0,
        num_errores=1 if estado_obra is EstadoObra.ERROR else 0,
        num_sin_subtitulos=1 if estado_obra is EstadoObra.SIN_SUBTITULOS else 0,
        num_sin_origen=1 if estado_obra is EstadoObra.SIN_ORIGEN else 0,
        idiomas=idiomas,
        dual=dual,
        ruta_bilingue=next((sub.ruta_bilingue for sub in subs if sub.ruta_bilingue), None),
        # Lo que costaría traducirla: los caracteres del origen, no de todos sus
        # subtítulos (una película con 25 idiomas no cuesta 25 veces más). La misma
        # cifra que reservaría el trabajo, para que la previsión de la interfaz cuadre.
        num_caracteres=caracteres_previstos(seleccion.origen) if seleccion.origen else 0,
        caracteres_exactos=seleccion.origen.metricas_exactas if seleccion.origen else True,
        origen_en_video=bool(seleccion.origen and seleccion.origen.es_pista),
        subtitulo_ids=[sub.id for sub in subs],
        subtitulo_origen_id=seleccion.origen.id if seleccion.origen else None,
        idioma_origen=seleccion.origen.idioma_origen if seleccion.origen else None,
        subtitulo_coreano_id=seleccion.coreano.id if seleccion.coreano else None,
    )


def _orden(rama: _Rama) -> str:
    """Orden alfabético insensible a mayúsculas, para que el listado sea previsible."""
    return rama.nombre.lower()

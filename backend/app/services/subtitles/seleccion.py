"""Selección del subtítulo de origen (y del coreano, si lo hay) de una obra.

Regla de negocio (plan de la Fase 3): el bilingüe se genera siempre desde un
subtítulo **español o inglés**, en ese orden de preferencia. Si la obra no tiene
ninguno válido, no es elegible. Si además tiene un coreano válido, el bilingüe sale
de fusionar los dos, sin traducir.

Además de la elección, se devuelve cada candidato con el motivo de su descarte, para
que la interfaz pueda enseñar por qué y dejar al usuario elegir otro.

Desde la Fase 5 los candidatos incluyen las **pistas incrustadas** del vídeo. Las
reglas son las mismas, con tres matices: una pista de imagen nunca sirve (no hay
OCR); una pista cuyas líneas aún no se conocen no se puede juzgar por su tamaño; y a
igualdad, un `.srt` externo gana a una pista, que antes habría que extraer.
"""

import re
from dataclasses import dataclass
from enum import Enum

from app.models.enums import FORMATOS_IMAGEN, EstadoSubtitulo, Idioma
from app.models.subtitle_file import ArchivoSubtitulo

# Idiomas válidos como origen, en orden de preferencia.
IDIOMAS_ORIGEN: tuple[Idioma, ...] = (Idioma.ES, Idioma.EN)
IDIOMA_DESTINO = Idioma.KO

# Un subtítulo con menos bloques que esta fracción del mayor de su obra es, casi
# seguro, un forzado que no lo dice en el nombre (solo carteles y rótulos). En la
# biblioteca real: 61 bloques frente a 2015 en *Mercy*, 191 frente a 1327 en
# *Conclave*.
PROPORCION_MINIMA_BLOQUES = 0.4
# Mínimo absoluto, para cuando el forzado encubierto es el único subtítulo de su obra
# y no hay con qué compararlo: *Thunderbolts* (33 bloques) o *Frankenstein* (90). La
# película real con menos diálogo de la biblioteca, *Eraserhead*, tiene 144.
MIN_BLOQUES = 100

# Variante latinoamericana del español, por el título de la pista o el nombre del
# fichero: `Latin American`, `Spanish[LAT]`, `NF_Spanish(Latin_America)`,
# `Español (Latinoamérica)`, `es-419`. Entre dos españoles se prefiere el castellano
# (decisión del usuario, Fase 5); el override manual sigue pudiendo elegir el latino.
_LATINO = re.compile(r"latin|\blat\b|latam|am[eé]rica|\b419\b", re.IGNORECASE)


class MotivoDescarte(str, Enum):
    """Por qué un subtítulo no puede ser ni origen ni coreano de su obra."""

    ERROR = "ERROR"  # no se pudo leer
    IMAGEN = "IMAGEN"  # pista de imagen (PGS, VobSub): sin OCR no hay texto
    IDIOMA = "IDIOMA"  # ni ES/EN ni KO (o desconocido)
    FORZADO = "FORZADO"  # el nombre lo declara forzado
    POCOS_BLOQUES = "POCOS_BLOQUES"  # forzado encubierto: muy corto para su obra


@dataclass(frozen=True, slots=True)
class Candidato:
    """Un subtítulo de la obra y, si no sirve, el motivo."""

    subtitulo: ArchivoSubtitulo
    descarte: MotivoDescarte | None


@dataclass(frozen=True, slots=True)
class Seleccion:
    """Resultado para una obra: el origen, el coreano y todos los candidatos."""

    origen: ArchivoSubtitulo | None
    coreano: ArchivoSubtitulo | None
    candidatos: list[Candidato]

    @property
    def elegible(self) -> bool:
        """Si se le puede generar el bilingüe: basta con tener origen ES/EN."""
        return self.origen is not None


def seleccionar(
    subtitulos: list[ArchivoSubtitulo], origen_preferido_id: int | None = None
) -> Seleccion:
    """Elige origen y coreano entre los subtítulos de una obra.

    `origen_preferido_id` es el override manual y gana a la heurística: el usuario
    puede saber que un subtítulo corto es completo (una película casi sin diálogo).
    Solo se ignora si apunta a algo que no puede ser origen de ninguna manera (otro
    idioma, o un fichero ilegible), porque daría un bilingüe inservible.
    """
    referencia = _bloques_de_referencia(subtitulos)
    candidatos = [Candidato(sub, _motivo_descarte(sub, referencia)) for sub in subtitulos]
    validos = [c.subtitulo for c in candidatos if c.descarte is None]

    origenes = [sub for sub in validos if sub.idioma_origen in IDIOMAS_ORIGEN]
    coreanos = [sub for sub in validos if sub.idioma_origen is IDIOMA_DESTINO]

    preferido = next(
        (
            c.subtitulo
            for c in candidatos
            if c.subtitulo.id == origen_preferido_id
            and c.descarte
            not in (MotivoDescarte.ERROR, MotivoDescarte.IMAGEN, MotivoDescarte.IDIOMA)
            and c.subtitulo.idioma_origen in IDIOMAS_ORIGEN
        ),
        None,
    )
    origen = preferido or min(origenes, key=_orden_origen, default=None)
    video_origen = origen.video_id if origen else None
    coreano = min(coreanos, key=lambda sub: _orden_coreano(sub, video_origen), default=None)
    return Seleccion(origen=origen, coreano=coreano, candidatos=candidatos)


def es_latino(sub: ArchivoSubtitulo) -> bool:
    """Si el subtítulo se anuncia como español de Latinoamérica."""
    return bool(_LATINO.search(f"{sub.titulo_pista or ''} {sub.nombre}"))


def _bloques_de_referencia(subtitulos: list[ArchivoSubtitulo]) -> int:
    """Tamaño del subtítulo completo de la obra, en cualquier idioma.

    No cuenta los SDH: con las acotaciones sonoras pueden doblar al resto (994
    bloques frente a ~430 en *Predator: Killer of Killers*) y harían pasar por
    forzado a un subtítulo completo. Tampoco los forzados declarados, claro.
    """
    # Solo cuentan las cifras exactas. Las de la cabecera de una pista sin extraer no
    # sirven para comparar: en un ASS de fansub los carteles y el karaoke de las
    # canciones se trocean en decenas de eventos (1023 «líneas» la inglesa de
    # *Jujutsu Kaisen* 01, frente a 390 la española, completa), y en una de imagen
    # cada línea cuenta dos veces (aparecer y borrarse).
    legibles = [
        sub
        for sub in subtitulos
        if sub.estado is not EstadoSubtitulo.ERROR and sub.metricas_exactas
    ]
    normales = [sub for sub in legibles if not (sub.es_sdh or sub.es_forzado)]
    return max((sub.num_bloques for sub in normales or legibles), default=0)


def _motivo_descarte(sub: ArchivoSubtitulo, referencia: int) -> MotivoDescarte | None:
    if sub.estado is EstadoSubtitulo.ERROR:
        return MotivoDescarte.ERROR
    if sub.formato in FORMATOS_IMAGEN:
        return MotivoDescarte.IMAGEN
    if sub.idioma_origen not in (*IDIOMAS_ORIGEN, IDIOMA_DESTINO):
        return MotivoDescarte.IDIOMA
    if sub.es_forzado:
        return MotivoDescarte.FORZADO
    # Con cifras exactas, la regla completa. Con las de la cabecera de una pista, solo
    # el mínimo absoluto: la proporción no es comparable (ver `_bloques_de_referencia`).
    # Y una pista sin estadísticas tiene 0 líneas hasta que se extrae: ahí 0 es «no se
    # sabe», no «vacía», y se le da el beneficio de la duda.
    if sub.metricas_exactas:
        minimo = max(MIN_BLOQUES, PROPORCION_MINIMA_BLOQUES * referencia)
    elif sub.bloques_conocidos:
        minimo = MIN_BLOQUES
    else:
        minimo = 0
    if sub.num_bloques < minimo:
        return MotivoDescarte.POCOS_BLOQUES
    return None


def _orden_origen(sub: ArchivoSubtitulo) -> tuple[int, bool, bool, bool, int, str]:
    """Clave de ordenación: primero el idioma preferido, luego sin SDH (las
    acotaciones sonoras son ruido en el bilingüe), luego el castellano antes que el
    latino, un `.srt` antes que una pista (se lee al momento; la pista hay que
    extraerla) y el más completo. La ruta solo desempata para que la elección sea
    estable entre escaneos."""
    return (
        IDIOMAS_ORIGEN.index(sub.idioma_origen),
        sub.es_sdh,
        sub.idioma_origen is Idioma.ES and es_latino(sub),
        sub.es_pista,
        -sub.num_bloques,
        sub.ruta,
    )


def _orden_coreano(sub: ArchivoSubtitulo, video_origen: int | None) -> tuple[bool, bool, int, str]:
    """Primero el coreano **de la misma procedencia que el origen**: si el origen es
    una pista, otra pista del mismo vídeo (en los MKV de Netflix las dos comparten los
    tiempos al milisegundo); si es un `.srt`, otro `.srt`."""
    return (sub.video_id != video_origen, sub.es_sdh, -sub.num_bloques, sub.ruta)

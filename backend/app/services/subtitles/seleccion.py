"""Selección del subtítulo de origen (y del coreano, si lo hay) de una obra.

Regla de negocio (plan de la Fase 3): el bilingüe se genera siempre desde un
subtítulo **español o inglés**, en ese orden de preferencia. Si la obra no tiene
ninguno válido, no es elegible. Si además tiene un coreano válido, el bilingüe sale
de fusionar los dos, sin traducir.

Además de la elección, se devuelve cada candidato con el motivo de su descarte, para
que la interfaz pueda enseñar por qué y dejar al usuario elegir otro.
"""

from dataclasses import dataclass
from enum import Enum

from app.models.enums import EstadoSubtitulo, Idioma
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


class MotivoDescarte(str, Enum):
    """Por qué un subtítulo no puede ser ni origen ni coreano de su obra."""

    ERROR = "ERROR"  # no se pudo leer
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
            and c.descarte not in (MotivoDescarte.ERROR, MotivoDescarte.IDIOMA)
            and c.subtitulo.idioma_origen in IDIOMAS_ORIGEN
        ),
        None,
    )
    origen = preferido or min(origenes, key=_orden_origen, default=None)
    coreano = min(coreanos, key=_orden_coreano, default=None)
    return Seleccion(origen=origen, coreano=coreano, candidatos=candidatos)


def _bloques_de_referencia(subtitulos: list[ArchivoSubtitulo]) -> int:
    """Tamaño del subtítulo completo de la obra, en cualquier idioma.

    No cuenta los SDH: con las acotaciones sonoras pueden doblar al resto (994
    bloques frente a ~430 en *Predator: Killer of Killers*) y harían pasar por
    forzado a un subtítulo completo. Tampoco los forzados declarados, claro.
    """
    legibles = [sub for sub in subtitulos if sub.estado is not EstadoSubtitulo.ERROR]
    normales = [sub for sub in legibles if not (sub.es_sdh or sub.es_forzado)]
    return max((sub.num_bloques for sub in normales or legibles), default=0)


def _motivo_descarte(sub: ArchivoSubtitulo, referencia: int) -> MotivoDescarte | None:
    if sub.estado is EstadoSubtitulo.ERROR:
        return MotivoDescarte.ERROR
    if sub.idioma_origen not in (*IDIOMAS_ORIGEN, IDIOMA_DESTINO):
        return MotivoDescarte.IDIOMA
    if sub.es_forzado:
        return MotivoDescarte.FORZADO
    if sub.num_bloques < max(MIN_BLOQUES, PROPORCION_MINIMA_BLOQUES * referencia):
        return MotivoDescarte.POCOS_BLOQUES
    return None


def _orden_origen(sub: ArchivoSubtitulo) -> tuple[int, bool, int, str]:
    """Clave de ordenación: primero el idioma preferido, luego sin SDH (las
    acotaciones sonoras son ruido en el bilingüe), luego el más completo. La ruta
    solo desempata para que la elección sea estable entre escaneos."""
    return (IDIOMAS_ORIGEN.index(sub.idioma_origen), sub.es_sdh, -sub.num_bloques, sub.ruta)


def _orden_coreano(sub: ArchivoSubtitulo) -> tuple[bool, int, str]:
    return (sub.es_sdh, -sub.num_bloques, sub.ruta)

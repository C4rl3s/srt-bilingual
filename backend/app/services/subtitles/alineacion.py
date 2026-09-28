"""Alineación de un subtítulo coreano ya existente con el de origen (modo fusión).

Cuando la obra ya trae un `.srt` coreano no hace falta traducir: basta con poner cada
frase coreana debajo de la frase de origen que le corresponde. El problema es que dos
subtítulos de fuentes distintas casi nunca cuadran: los tiempos van desfasados (a
veces también a otra velocidad, si vienen de versiones a 25 y 23,976 fps) y cada uno
corta las frases por sitios distintos.

Los tiempos del **origen mandan**, igual que al traducir: el resultado es un texto
coreano por bloque de origen, y el generador de bilingües no distingue si viene de
DeepL o de aquí.

Pasos:

1. **Desfase global.** Se prueban desplazamientos y factores de velocidad del
   coreano y se queda el que más tiempo en pantalla comparte con el origen.
2. **Vía rápida 1:1.** Si hay tantos bloques de un lado como del otro y, ya
   corregidos, cada par se solapa, el bloque coreano `i` va con el de origen `i`.
3. **Vía general.** Cada bloque coreano va con el bloque de origen con el que más se
   solapa; si uno de origen recibe varios, se unen en orden.
4. **Calidad**: fracción de bloques coreanos bien colocados. Por debajo del umbral,
   el coreano es probablemente de otra versión y no se fusiona sin preguntar.
"""

from bisect import bisect_left
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum

from app.services.subtitles.modelo import Bloque

# Factores de velocidad a probar: misma versión, y las conversiones PAL ↔ cine.
FACTORES = (1.0, 25 / 23.976, 23.976 / 25)
# Búsqueda del desplazamiento: primero gruesa y amplia, luego fina alrededor del mejor.
RANGO_GRUESO_S = 60.0
PASO_GRUESO_S = 0.5
PASO_FINO_S = 0.05
# Un bloque coreano sin solape con ninguno de origen se acepta en el más cercano si
# está a menos de esto (los huecos entre frases seguidas son de décimas).
TOLERANCIA_HUECO_S = 0.5
# Más de lo que dura cualquier subtítulo: acota la búsqueda hacia atrás de bloques de
# origen que aún podrían solaparse con uno coreano.
DURACION_MAXIMA_S = 15.0
# Un bloque coreano está "bien colocado" si comparte con su bloque de origen al menos
# esta fracción de su propia duración.
SOLAPE_MINIMO = 0.5
# Fracción de bloques coreanos bien colocados por debajo de la cual la alineación no
# se da por buena. Calibrado con la biblioteca real: las 11 parejas de verdad dan
# entre 0,75 y 1,00, y el coreano de una película contra el origen de otra (control
# negativo) no pasa de 0,58: en películas con mucho diálogo, el azar ya solapa mucho.
UMBRAL_CALIDAD = 0.7


class MetodoAlineacion(str, Enum):
    UNO_A_UNO = "UNO_A_UNO"  # mismo número de bloques y todos los pares se solapan
    SOLAPE = "SOLAPE"  # asignación por máximo solape


@dataclass(frozen=True, slots=True)
class ResultadoAlineacion:
    """Un texto coreano por bloque de origen (cadena vacía si no le toca ninguno)."""

    textos: list[str]
    desplazamiento: timedelta
    factor: float
    metodo: MetodoAlineacion
    calidad: float
    # Bloques coreanos que no encontraron sitio (su texto no aparece en `textos`).
    descolocados: int

    @property
    def aceptable(self) -> bool:
        return self.calidad >= UMBRAL_CALIDAD


# Un intervalo en segundos: más cómodo y rápido que `timedelta` para la aritmética.
type _Intervalo = tuple[float, float]


def alinear(origen: list[Bloque], coreano: list[Bloque]) -> ResultadoAlineacion:
    """Reparte el texto de `coreano` sobre los bloques de `origen`."""
    tramos_origen = [_segundos(b) for b in origen]
    tramos_coreano = [_segundos(b) for b in coreano]
    factor, desplazamiento = _mejor_transformacion(tramos_origen, tramos_coreano)
    corregidos = [_transformar(t, factor, desplazamiento) for t in tramos_coreano]

    if _es_uno_a_uno(tramos_origen, corregidos):
        textos = [b.contenido for b in coreano]
        calidad = _calidad(tramos_origen, corregidos, list(range(len(coreano))))
        return ResultadoAlineacion(
            textos=textos,
            desplazamiento=timedelta(seconds=desplazamiento),
            factor=factor,
            metodo=MetodoAlineacion.UNO_A_UNO,
            calidad=calidad,
            descolocados=0,
        )

    asignacion = _asignar_por_solape(tramos_origen, corregidos)
    por_bloque: list[list[str]] = [[] for _ in origen]
    for indice_coreano, indice_origen in enumerate(asignacion):
        if indice_origen is not None:
            por_bloque[indice_origen].append(coreano[indice_coreano].contenido)

    return ResultadoAlineacion(
        textos=["\n".join(partes) for partes in por_bloque],
        desplazamiento=timedelta(seconds=desplazamiento),
        factor=factor,
        metodo=MetodoAlineacion.SOLAPE,
        calidad=_calidad(tramos_origen, corregidos, asignacion),
        descolocados=sum(indice is None for indice in asignacion),
    )


def _segundos(bloque: Bloque) -> _Intervalo:
    return (bloque.inicio.total_seconds(), bloque.fin.total_seconds())


def _transformar(tramo: _Intervalo, factor: float, desplazamiento: float) -> _Intervalo:
    return (tramo[0] * factor + desplazamiento, tramo[1] * factor + desplazamiento)


def _solape(a: _Intervalo, b: _Intervalo) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def _solape_total(origen: list[_Intervalo], otro: list[_Intervalo]) -> float:
    """Tiempo en pantalla compartido por dos listas ordenadas de intervalos.

    Recorre las dos a la vez avanzando siempre la que termina antes: coste lineal,
    que importa porque se evalúa cientos de veces por película.
    """
    total = 0.0
    i = j = 0
    while i < len(origen) and j < len(otro):
        total += _solape(origen[i], otro[j])
        if origen[i][1] < otro[j][1]:
            i += 1
        else:
            j += 1
    return total


def _mejor_transformacion(
    origen: list[_Intervalo], coreano: list[_Intervalo]
) -> tuple[float, float]:
    """(factor, desplazamiento en s) que maximiza el solape con el origen."""
    origen = sorted(origen)
    coreano = sorted(coreano)

    def puntuar(factor: float, desplazamiento: float) -> float:
        return _solape_total(origen, [_transformar(t, factor, desplazamiento) for t in coreano])

    pasos = int(RANGO_GRUESO_S / PASO_GRUESO_S)
    gruesos = [k * PASO_GRUESO_S for k in range(-pasos, pasos + 1)]
    # El 0 va primero para que, a igualdad de puntuación, gane no mover nada.
    candidatos = [(f, d) for f in FACTORES for d in sorted(gruesos, key=abs)]
    factor, desplazamiento = max(candidatos, key=lambda c: puntuar(*c))

    finos = [desplazamiento + k * PASO_FINO_S for k in range(-10, 11)]
    desplazamiento = max(sorted(finos, key=abs), key=lambda d: puntuar(factor, d))
    return factor, round(desplazamiento, 3)


def _es_uno_a_uno(origen: list[_Intervalo], coreano: list[_Intervalo]) -> bool:
    """Mismo número de bloques y cada par `i`-ésimo se solapa de verdad.

    Contar no basta: dos ficheros pueden coincidir en número con las frases cortadas
    en sitios distintos, y entonces los pares quedarían desplazados.
    """
    return len(origen) == len(coreano) and all(
        _solape(o, c) > 0 for o, c in zip(origen, coreano, strict=True)
    )


def _asignar_por_solape(origen: list[_Intervalo], coreano: list[_Intervalo]) -> list[int | None]:
    """Para cada bloque coreano, el índice del bloque de origen donde va (o `None`)."""
    orden = sorted(range(len(origen)), key=lambda i: origen[i][0])
    inicios = [origen[i][0] for i in orden]
    asignacion: list[int | None] = []

    for tramo in coreano:
        # Candidatos: los de origen que empiezan antes de que acabe este bloque, sin
        # retroceder más de lo que puede durar un subtítulo.
        fin_busqueda = bisect_left(inicios, tramo[1])
        inicio_busqueda = bisect_left(inicios, tramo[0] - DURACION_MAXIMA_S)
        cercanos = orden[inicio_busqueda:fin_busqueda]
        mejor = max(cercanos, key=lambda i: _solape(origen[i], tramo), default=None)

        if mejor is not None and _solape(origen[mejor], tramo) > 0:
            asignacion.append(mejor)
            continue
        # Sin solape: el más cercano en el tiempo, si está a un hueco de distancia.
        vecinos = orden[max(0, fin_busqueda - 1) : fin_busqueda + 1]
        cercano = min(vecinos, key=lambda i: _distancia(origen[i], tramo), default=None)
        if cercano is not None and _distancia(origen[cercano], tramo) <= TOLERANCIA_HUECO_S:
            asignacion.append(cercano)
        else:
            asignacion.append(None)
    return asignacion


def _distancia(a: _Intervalo, b: _Intervalo) -> float:
    """Separación entre dos intervalos que no se tocan (0 si se solapan)."""
    return max(0.0, max(a[0], b[0]) - min(a[1], b[1]))


def _calidad(
    origen: list[_Intervalo], coreano: list[_Intervalo], asignacion: list[int | None]
) -> float:
    """Fracción de bloques coreanos que comparten con su bloque de origen al menos
    `SOLAPE_MINIMO` de su propia duración."""
    if not coreano:
        return 0.0
    bien = 0
    for tramo, indice in zip(coreano, asignacion, strict=True):
        duracion = tramo[1] - tramo[0]
        if indice is not None and duracion > 0:
            bien += _solape(origen[indice], tramo) >= SOLAPE_MINIMO * duracion
    return bien / len(coreano)

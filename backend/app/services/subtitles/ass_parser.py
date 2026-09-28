"""Parser de subtítulos ASS/SSA (el formato del 73 % de las pistas de la biblioteca).

Convierte el ASS a `list[Bloque]`, como hace `srt_parser` con los `.srt`, para que el
resto del dominio (traducir, alinear, generar el bilingüe) no distinga el formato.

No se usa la conversión de `ffmpeg` (ASS → SRT): mete etiquetas
`<font face=… size=…><b>` en cada línea, y no filtra nada. Aquí se lee el ASS
directamente y se queda solo el **diálogo**:

- Solo líneas `Dialogue:` de la sección `[Events]`, con el orden de campos que
  declare su línea `Format:` (el texto es siempre el último y puede llevar comas).
- Fuera las etiquetas de estilo `{\\...}`; `\\N` y `\\n` son saltos de línea y `\\h`,
  un espacio duro.
- Se descartan los **carteles**: los estilos con nombre de cartel (`Sign`,
  `Typeset`, `EndCard`…), las líneas posicionadas a mano (`\\pos`, `\\move`: rótulos
  pegados a un objeto de la imagen) y los dibujos vectoriales (`\\p1`). Tampoco las
  letras de las canciones con **karaoke** (`\\k`) ni los estilos de opening y
  ending. Mezclados con el diálogo, en el bilingüe saldrían frases sueltas de
  carteles a destiempo y cada sílaba del karaoke por separado.
- Un mismo texto en el mismo instante en varias capas (sombra, borde) queda una
  sola vez.
- Ordenado por inicio: el ASS no obliga a escribir las líneas en orden.
"""

import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from app.services.subtitles.modelo import Bloque
from app.services.subtitles.srt_parser import leer_texto

# Estilos que no son diálogo, por su nombre. `\b` no sirve para `OP`/`ED` pegados a
# otras palabras con guion bajo (`OP_Romaji`), así que se buscan como palabra entre
# separadores cualquiera. `Cart` es la abreviatura de cartel del fansub español de
# *Jujutsu Kaisen* (`Cart_A_Tre`: «Club de ocultismo», «Acta de defunción»).
_ESTILO_NO_DIALOGO = re.compile(
    r"sign|cart(?:el|[^a-z]|$)|typeset|endcard|karaoke|romaji|kanji|lyric|letra|song|canci[oó]n|"
    r"(?:^|[^a-z])(?:op|ed|opening|ending|insert)(?:[^a-z]|$)",
    re.IGNORECASE,
)
# Etiquetas de estilo que delatan un cartel o un efecto: posición o movimiento
# fijados a mano, dibujo vectorial y sílabas de karaoke.
_ETIQUETA_NO_DIALOGO = re.compile(r"\\(?:pos|move)\(|\\p[1-9]|\\[kK][fo]?\d")
_ETIQUETAS = re.compile(r"\{[^}]*\}")
_TIEMPO = re.compile(r"(\d+):(\d{1,2}):(\d{1,2})[.:](\d{1,3})")


class ErrorAss(ValueError):
    """El fichero no tiene la estructura mínima de un ASS."""


@dataclass(frozen=True, slots=True)
class _Evento:
    inicio: timedelta
    fin: timedelta
    estilo: str
    texto: str  # el campo crudo, con etiquetas


def parsear(ruta: Path) -> list[Bloque]:
    """Parsea un `.ass`/`.ssa` y devuelve su diálogo como `list[Bloque]`."""
    return parsear_texto(leer_texto(ruta))


def parsear_texto(contenido: str) -> list[Bloque]:
    """Como `parsear`, sobre el texto ya leído (lo usan los tests)."""
    eventos = _eventos(contenido)
    vistos: set[tuple[timedelta, timedelta, str]] = set()
    dialogo: list[tuple[timedelta, timedelta, str]] = []
    for evento in eventos:
        if not es_dialogo(evento.estilo, evento.texto):
            continue
        texto = limpiar(evento.texto)
        clave = (evento.inicio, evento.fin, texto)
        if not texto or clave in vistos:
            continue
        vistos.add(clave)
        dialogo.append(clave)

    # `sorted` es estable: dos líneas que empiezan a la vez conservan su orden.
    dialogo.sort(key=lambda d: d[0])
    return [
        Bloque(indice=i, inicio=inicio, fin=fin, contenido=texto)
        for i, (inicio, fin, texto) in enumerate(dialogo, 1)
    ]


def es_dialogo(estilo: str, texto: str) -> bool:
    """Si una línea es diálogo, y no un cartel, un dibujo o una canción."""
    return not _ESTILO_NO_DIALOGO.search(estilo) and not _ETIQUETA_NO_DIALOGO.search(texto)


def limpiar(texto: str) -> str:
    """Texto visible de una línea ASS: sin etiquetas y con los saltos de línea reales."""
    texto = _ETIQUETAS.sub("", texto)
    texto = texto.replace("\\N", "\n").replace("\\n", "\n").replace("\\h", " ")
    lineas = (" ".join(linea.split()) for linea in texto.split("\n"))
    return "\n".join(linea for linea in lineas if linea)


def _eventos(contenido: str) -> list[_Evento]:
    campos: list[str] | None = None
    en_eventos = False
    eventos: list[_Evento] = []

    for linea in contenido.splitlines():
        linea = linea.strip()
        if linea.startswith("["):
            en_eventos = linea.lower() == "[events]"
            continue
        if not en_eventos or ":" not in linea:
            continue
        tipo, _, resto = linea.partition(":")
        tipo = tipo.strip().lower()
        if tipo == "format":
            campos = [campo.strip().lower() for campo in resto.split(",")]
        elif tipo == "dialogue":
            if campos is None:
                raise ErrorAss("Línea Dialogue antes de la línea Format de [Events]")
            valores = [valor.strip() for valor in resto.split(",", len(campos) - 1)]
            if len(valores) < len(campos):
                continue  # línea truncada: no se puede interpretar
            fila = dict(zip(campos, valores, strict=True))
            eventos.append(
                _Evento(
                    inicio=_tiempo(fila.get("start", "")),
                    fin=_tiempo(fila.get("end", "")),
                    estilo=fila.get("style", ""),
                    texto=fila.get("text", valores[-1]),
                )
            )

    if campos is None:
        raise ErrorAss("No tiene sección [Events] con línea Format")
    return eventos


def _tiempo(valor: str) -> timedelta:
    """`H:MM:SS.cc` (centésimas) → `timedelta`."""
    coincidencia = _TIEMPO.fullmatch(valor.strip())
    if coincidencia is None:
        raise ErrorAss(f"Marca de tiempo no válida: {valor!r}")
    horas, minutos, segundos, fraccion = coincidencia.groups()
    # La fracción son centésimas en ASS; se interpreta por su número de cifras.
    milisegundos = int(fraccion.ljust(3, "0")[:3])
    return timedelta(
        hours=int(horas), minutes=int(minutos), seconds=int(segundos), milliseconds=milisegundos
    )

"""Generación del `.srt` bilingüe.

Es el punto entero del proyecto: cada bloque del subtítulo de origen conserva su
índice y sus marcas de tiempo **tal cual**, y debajo de su texto se añade el coreano:

    12
    00:01:23,400 --> 00:01:25,900
    Texto original en español
    한국어 번역

Recibe **bloques y textos**, no rutas: no sabe ni le importa si el coreano lo tradujo
DeepL o viene de alinear un subtítulo que ya existía, ni si el origen era un `.srt`
o (en la Fase 5) una pista extraída de un MKV. Adónde se escribe lo decide quien
llama.
"""

import os
import tempfile
from pathlib import Path

import srt

from app.services.subtitles.modelo import Bloque


class ErrorGeneracion(Exception):
    """Los textos coreanos no encajan con los bloques de origen."""


def componer(bloques_origen: list[Bloque], textos_coreano: list[str]) -> list[Bloque]:
    """Bloques bilingües: el original y, debajo, su coreano.

    Un bloque sin coreano (en la fusión, una frase que el coreano no traduce) se
    queda solo con el original, en vez de llevar una línea vacía.
    """
    # La invariante de `Translator` y de la alineación, verificada aquí también: si
    # no hay exactamente un texto por bloque, el emparejamiento no es de fiar.
    if len(textos_coreano) != len(bloques_origen):
        raise ErrorGeneracion(
            f"{len(textos_coreano)} textos coreanos para {len(bloques_origen)} bloques de origen"
        )
    return [
        Bloque(
            indice=bloque.indice,
            inicio=bloque.inicio,
            fin=bloque.fin,
            contenido=_unir(bloque.contenido, coreano),
        )
        for bloque, coreano in zip(bloques_origen, textos_coreano, strict=True)
    ]


def _unir(original: str, coreano: str) -> str:
    original, coreano = original.strip(), coreano.strip()
    return f"{original}\n{coreano}" if coreano else original


def escribir(bloques: list[Bloque], ruta_destino: Path) -> Path:
    """Escribe los bloques como `.srt` UTF-8, de forma **atómica**.

    Primero a un temporal en la misma carpeta y, al final, un renombrado. Así un fallo
    a medias (la biblioteca está en una unidad de red) nunca deja un `.bilingue.srt`
    truncado que el siguiente escaneo tomaría por "ya traducido". El renombrado es
    atómico solo dentro del mismo volumen: por eso el temporal va junto al destino y
    no en la carpeta temporal del sistema.
    """
    subtitulos = [
        srt.Subtitle(index=b.indice, start=b.inicio, end=b.fin, content=b.contenido)
        for b in bloques
    ]
    # `reindex=False`: la numeración original se conserva, como los tiempos.
    contenido = srt.compose(subtitulos, reindex=False)

    ruta_destino.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporal = tempfile.mkstemp(
        dir=ruta_destino.parent, prefix=f".{ruta_destino.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as fichero:
            fichero.write(contenido)
        os.replace(temporal, ruta_destino)
    except BaseException:
        Path(temporal).unlink(missing_ok=True)
        raise
    return ruta_destino


def generar(bloques_origen: list[Bloque], textos_coreano: list[str], ruta_destino: Path) -> Path:
    """Compone el bilingüe y lo escribe en `ruta_destino`."""
    return escribir(componer(bloques_origen, textos_coreano), ruta_destino)

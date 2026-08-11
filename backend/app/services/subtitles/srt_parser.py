"""Parser de ficheros `.srt` y utilidades de conteo / detección de idioma.

Convierte el `.srt` a la representación normalizada `Bloque`, de forma que el resto
del dominio no dependa de la librería `srt`.
"""

from pathlib import Path

import srt

from app.models.enums import SUFIJOS_IDIOMA, TOKENS_FLAG, Idioma
from app.services.subtitles.modelo import Bloque


def _leer_texto(ruta: Path) -> str:
    """Lee el fichero como texto manejando BOM y un fallback latino habitual en
    bibliotecas antiguas."""
    datos = ruta.read_bytes()
    try:
        return datos.decode("utf-8-sig")
    except UnicodeDecodeError:
        return datos.decode("latin-1")


def parsear(ruta: Path) -> list[Bloque]:
    """Parsea un `.srt` y devuelve sus subtítulos como `list[Bloque]`.

    Lanza excepción si el contenido está malformado (lo gestiona el scanner).
    """
    contenido = _leer_texto(ruta)
    return [
        Bloque(indice=sub.index, inicio=sub.start, fin=sub.end, contenido=sub.content)
        for sub in srt.parse(contenido)
    ]


def contar_caracteres(bloques: list[Bloque]) -> int:
    """Caracteres de texto (sin índices ni marcas de tiempo), espacios incluidos."""
    return sum(len(bloque.contenido.strip()) for bloque in bloques)


def contar_bloques(bloques: list[Bloque]) -> int:
    """Número de subtítulos (cues) del fichero."""
    return len(bloques)


def detectar_idioma_desde_nombre(nombre: str) -> Idioma:
    """Deduce el idioma de origen del nombre de fichero por su sufijo.

    Recorre los tokens de derecha a izquierda saltando flags (`forced`, `sdh`…);
    el primer token no-flag es el candidato a idioma. Así `pelicula.es.forced.srt`
    → ES y `It.2017.srt` → UNKNOWN (no confunde el título con un idioma).
    """
    partes = nombre.split(".")
    if len(partes) > 1:  # descartar la extensión
        partes = partes[:-1]
    for token in reversed(partes):
        clave = token.lower()
        if clave in TOKENS_FLAG:
            continue
        return SUFIJOS_IDIOMA.get(clave, Idioma.UNKNOWN)
    return Idioma.UNKNOWN

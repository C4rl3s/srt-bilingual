"""Convención de nombre del subtítulo bilingüe generado.

El `.srt` bilingüe es la prueba en disco de que un subtítulo ya está traducido, así
que su nombre es estructural: el scanner lo deriva para detectar lo ya traducido y
lo reconoce para excluirlo como fuente de escaneo.

Formato:  ``<base>.<ORIGEN>-<DESTINO>.bilingue.srt``
Ejemplo:  ``Pelicula.es.srt`` (origen ES, destino KO) → ``Pelicula.ES-KO.bilingue.srt``
"""

from pathlib import Path

from app.models.enums import SUFIJOS_IDIOMA, TOKENS_FLAG, Idioma

SUFIJO_BILINGUE = ".bilingue.srt"


def base_sin_idioma(ruta_origen: Path) -> str:
    """Nombre del original sin extensión `.srt` ni el sufijo de idioma y flags.

    `Pelicula.es.srt` → `Pelicula`; `Pelicula.en.forced.srt` → `Pelicula`;
    `Pelicula.srt` → `Pelicula`.

    Es además la **clave de agrupación por obra**: los subtítulos de un mismo
    capítulo en varios idiomas (`.es`, `.en`) comparten base con su vídeo, y así el
    árbol de la biblioteca los presenta como una sola hoja.
    """
    tronco = ruta_origen.name[: -len(".srt")] if ruta_origen.suffix == ".srt" else ruta_origen.stem
    partes = tronco.split(".")
    # Mismo criterio que `srt_parser.analizar_nombre`: el sufijo son flags y, como
    # mucho, un idioma. Se deja siempre al menos una parte (el título).
    visto_idioma = False
    while len(partes) > 1:
        token = partes[-1].lower()
        if token in TOKENS_FLAG:
            partes.pop()
        elif not visto_idioma and token in SUFIJOS_IDIOMA:
            visto_idioma = True
            partes.pop()
        else:
            break
    return ".".join(partes)


def derivar_nombre_bilingue(ruta_origen: Path, origen: Idioma, destino: Idioma) -> Path:
    """Ruta determinista del bilingüe correspondiente a `ruta_origen`."""
    base = base_sin_idioma(ruta_origen)
    nombre = f"{base}.{origen.value}-{destino.value}{SUFIJO_BILINGUE}"
    return ruta_origen.with_name(nombre)


def es_fichero_bilingue(nombre: str) -> bool:
    """`True` si el nombre corresponde a un bilingüe generado (para excluirlo)."""
    return nombre.endswith(SUFIJO_BILINGUE)

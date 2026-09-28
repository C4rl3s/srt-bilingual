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


def ruta_bilingue_de_obra(
    directorio: Path, nombre_obra: str, origen: Idioma, destino: Idioma = Idioma.KO
) -> Path:
    """Dónde va el bilingüe de una obra: en su carpeta y con su nombre (el del vídeo).

    Aunque el origen viva en `Subs\\English.srt`, el bilingüe se escribe junto al
    vídeo y con la base del vídeo, que es donde Plex lo busca; `English.EN-KO…` no
    le diría a Plex de qué película es.
    """
    return directorio / f"{nombre_obra}.{origen.value}-{destino.value}{SUFIJO_BILINGUE}"


def derivar_nombre_bilingue(ruta_origen: Path, origen: Idioma, destino: Idioma) -> Path:
    """Ruta determinista del bilingüe correspondiente a `ruta_origen`, junto a él."""
    return ruta_bilingue_de_obra(ruta_origen.parent, base_sin_idioma(ruta_origen), origen, destino)


def es_fichero_bilingue(nombre: str) -> bool:
    """`True` si el nombre corresponde a un bilingüe generado (para excluirlo)."""
    return nombre.endswith(SUFIJO_BILINGUE)

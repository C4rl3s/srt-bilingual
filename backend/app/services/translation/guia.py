"""Guía de traducción de una serie: glosario e instrucciones para el proveedor.

Una obra es un capítulo, pero los nombres y términos son de toda la serie. La guía es
un fichero `srt-bilingual.toml` en la carpeta de la serie, dentro de la biblioteca:

```toml
[glosario]            # español = coreano
"Marley" = "마레"
"titán acorazado" = "갑옷 거인"

[instrucciones]
lista = ["Korean subtitles for Attack on Titan...", "..."]
```

Vive en disco y no en la base de datos por el principio del proyecto: la BD es un
índice reconstruible y la guía la escribe el usuario, así que no se puede
reconstruir. Así viaja con la biblioteca.

Al traducir una obra se busca subiendo desde su carpeta hasta la raíz de la carpeta
de biblioteca, y gana la más cercana: una temporada puede tener la suya.

Plan y motivos: `docs/plans/plan-glosario-por-obra.md`.
"""

import hashlib
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

from app.services.translation.base import ErrorTraduccion

NOMBRE_FICHERO = "srt-bilingual.toml"

# Límites de `custom_instructions` en la API de DeepL.
MAX_INSTRUCCIONES = 10
MAX_LARGO_INSTRUCCION = 300

_SECCIONES = {"glosario", "instrucciones"}
_CLAVES_INSTRUCCIONES = {"lista"}


class GuiaInvalida(ErrorTraduccion):
    """El fichero de la guía existe pero no se puede usar. Hereda de `ErrorTraduccion`
    para que un trabajo que la encuentre así falle con el motivo, en vez de traducir
    sin ella en silencio."""


@dataclass(frozen=True, slots=True)
class Guia:
    """Glosario (español → coreano) e instrucciones de una serie."""

    ruta: Path
    glosario: dict[str, str]
    instrucciones: tuple[str, ...]

    @property
    def huella(self) -> str:
        """Identifica el contenido, no el fichero: cambiar un comentario o el orden de
        las entradas no la cambia. Sirve para reutilizar el glosario ya creado en el
        proveedor mientras la guía no cambie."""
        contenido = json.dumps(
            [sorted(self.glosario.items()), list(self.instrucciones)], ensure_ascii=False
        )
        return hashlib.sha256(contenido.encode("utf-8")).hexdigest()[:16]


def buscar(directorio: Path, raiz: Path) -> Path | None:
    """El fichero de guía más cercano subiendo de `directorio` a `raiz` (incluida).

    Nunca sube por encima de la raíz: una guía de fuera de la carpeta de biblioteca
    no es de esta obra.
    """
    if not directorio.is_relative_to(raiz):
        return None
    for carpeta in (directorio, *directorio.parents):
        candidato = carpeta / NOMBRE_FICHERO
        if candidato.is_file():
            return candidato
        if carpeta == raiz:
            break
    return None


def guia_de(directorio: Path, raiz: Path) -> Guia | None:
    """La guía que corresponde a una obra de `directorio`, o `None` si no hay."""
    ruta = buscar(directorio, raiz)
    return leer(ruta) if ruta else None


def leer(ruta: Path) -> Guia:
    """Lee y valida un fichero de guía. Cualquier problema es `GuiaInvalida`."""
    try:
        with ruta.open("rb") as fichero:
            datos = tomllib.load(fichero)
    except tomllib.TOMLDecodeError as exc:
        raise GuiaInvalida(f"{ruta}: no es TOML válido ({exc})") from exc
    except OSError as exc:
        raise GuiaInvalida(f"{ruta}: no se puede leer ({exc})") from exc

    desconocidas = set(datos) - _SECCIONES
    if desconocidas:
        raise GuiaInvalida(
            f"{ruta}: secciones desconocidas {sorted(desconocidas)}; "
            f"se admiten {sorted(_SECCIONES)}"
        )
    glosario = _glosario(ruta, datos.get("glosario", {}))
    instrucciones = _instrucciones(ruta, datos.get("instrucciones", {}))
    if not glosario and not instrucciones:
        raise GuiaInvalida(f"{ruta}: la guía está vacía (ni glosario ni instrucciones)")
    return Guia(ruta=ruta, glosario=glosario, instrucciones=instrucciones)


def _glosario(ruta: Path, seccion: object) -> dict[str, str]:
    if not isinstance(seccion, dict):
        raise GuiaInvalida(f"{ruta}: [glosario] debe ser una tabla de «español = coreano»")
    glosario: dict[str, str] = {}
    for origen, destino in seccion.items():
        if not isinstance(destino, str):
            raise GuiaInvalida(f"{ruta}: en [glosario], {origen!r} debe ser un texto")
        origen, destino = origen.strip(), destino.strip()
        if not origen or not destino:
            raise GuiaInvalida(f"{ruta}: en [glosario] hay una entrada vacía ({origen!r})")
        # DeepL recibe el glosario como TSV: un tabulador o un salto lo rompería.
        if any(c in texto for texto in (origen, destino) for c in "\t\r\n"):
            raise GuiaInvalida(
                f"{ruta}: en [glosario], {origen!r} lleva tabuladores o saltos de línea"
            )
        # Las variantes de mayúsculas no son duplicados: el glosario distingue
        # mayúsculas, y «isla Paradis» e «Isla Paradis» hacen falta las dos.
        glosario[origen] = destino
    return glosario


def _instrucciones(ruta: Path, seccion: object) -> tuple[str, ...]:
    if not isinstance(seccion, dict) or set(seccion) - _CLAVES_INSTRUCCIONES:
        raise GuiaInvalida(f"{ruta}: [instrucciones] solo admite «lista = [...]»")
    lista = seccion.get("lista", [])
    if not isinstance(lista, list) or not all(isinstance(i, str) for i in lista):
        raise GuiaInvalida(f"{ruta}: [instrucciones] lista debe ser una lista de textos")
    instrucciones = tuple(i.strip() for i in lista)
    if len(instrucciones) > MAX_INSTRUCCIONES:
        raise GuiaInvalida(
            f"{ruta}: hay {len(instrucciones)} instrucciones y el máximo es {MAX_INSTRUCCIONES}"
        )
    for numero, instruccion in enumerate(instrucciones, start=1):
        if not instruccion:
            raise GuiaInvalida(f"{ruta}: la instrucción {numero} está vacía")
        if len(instruccion) > MAX_LARGO_INSTRUCCION:
            raise GuiaInvalida(
                f"{ruta}: la instrucción {numero} tiene {len(instruccion)} caracteres "
                f"y el máximo es {MAX_LARGO_INSTRUCCION}"
            )
    return instrucciones

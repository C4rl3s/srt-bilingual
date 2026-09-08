"""Router del explorador de disco que alimenta el selector de carpetas.

Hace falta porque el navegador **no puede** dar la ruta absoluta de una carpeta: un
`<input type="file" webkitdirectory>` solo devuelve rutas relativas al directorio
elegido. Así que la navegación la sirve el backend, que sí ve el disco.

Solo lista directorios (los ficheros no pintan nada aquí) y es de solo lectura.
Como expone la estructura de carpetas de la máquina, el servidor debe escuchar en
`127.0.0.1`; ver el aviso del README.
"""

import os
import string
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.filesystem import EntradaDirectorio, ListadoDirectorio

router = APIRouter(tags=["filesystem"])


@router.get("/fs/roots", response_model=list[EntradaDirectorio])
def listar_raices() -> list[EntradaDirectorio]:
    """Puntos de partida de la navegación: unidades en Windows, `/` y `~` fuera."""
    if sys.platform == "win32":
        return [
            EntradaDirectorio(nombre=f"{letra}:", ruta=f"{letra}:\\")
            for letra in string.ascii_uppercase
            if Path(f"{letra}:\\").exists()
        ]

    return [
        EntradaDirectorio(nombre="/", ruta="/"),
        EntradaDirectorio(nombre="~", ruta=str(Path.home())),
    ]


@router.get("/fs/browse", response_model=ListadoDirectorio)
def navegar(ruta: str = Query(description="Ruta absoluta a listar")) -> ListadoDirectorio:
    """Subdirectorios de `ruta`, ordenados, para pintar un nivel del explorador."""
    destino = Path(ruta).expanduser()
    if not destino.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La ruta no existe o no es una carpeta: {ruta}",
        )
    destino = destino.resolve()

    try:
        with os.scandir(destino) as entradas:
            directorios = [_a_entrada(e) for e in entradas if _es_carpeta(e)]
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Sin permiso para abrir {destino}. Si es una carpeta de un recurso "
                "compartido, puede ser un enlace que apunta fuera del recurso: eso no "
                "se puede seguir desde este equipo."
            ),
        ) from None

    directorios.sort(key=lambda item: item.nombre.lower())

    # En la raíz de una unidad, `parent` devuelve la propia raíz: eso significa que
    # ya no se puede subir más.
    padre = destino.parent
    return ListadoDirectorio(
        ruta=str(destino),
        padre=None if padre == destino else str(padre),
        directorios=directorios,
    )


def _es_carpeta(entrada: os.DirEntry[str]) -> bool:
    """Descarta ficheros y ocultos, quedándose con los directorios.

    `follow_symlinks=False` es la clave: un *reparse point* (junction, symlink) se
    reconoce como directorio **sin** intentar seguirlo. Con el comportamiento por
    defecto, una junction cuyo destino está en otro equipo devuelve `False` y la
    carpeta desaparecía del listado sin explicación.
    """
    if entrada.name.startswith("."):
        return False
    try:
        return entrada.is_dir(follow_symlinks=False) or entrada.is_dir()
    except OSError:
        return False


def _a_entrada(entrada: os.DirEntry[str]) -> EntradaDirectorio:
    """Marca si la carpeta se puede abrir de verdad desde este equipo.

    Ojo con `entrada.is_dir()`: `os.scandir` reutiliza los atributos que ya venían
    en el listado del directorio padre, así que una junction rota devuelve `True`
    sin haber intentado seguirla jamás. Un `stat` nuevo sobre la ruta sí la sigue,
    que es justo lo que fallará cuando el usuario intente entrar.
    """
    try:
        accesible = Path(entrada.path).is_dir()
    except OSError:
        accesible = False

    return EntradaDirectorio(
        nombre=entrada.name,
        ruta=entrada.path,
        accesible=accesible,
        motivo=None if accesible else "Enlace a otro equipo o destino no disponible",
    )

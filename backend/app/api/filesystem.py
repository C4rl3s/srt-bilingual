"""Router del explorador de disco que alimenta el selector de carpetas.

Hace falta porque el navegador **no puede** dar la ruta absoluta de una carpeta: un
`<input type="file" webkitdirectory>` solo devuelve rutas relativas al directorio
elegido. Así que la navegación la sirve el backend, que sí ve el disco.

Solo lista directorios (los ficheros no pintan nada aquí) y es de solo lectura.
Como expone la estructura de carpetas de la máquina, el servidor debe escuchar en
`127.0.0.1`; ver el aviso del README.
"""

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

    directorios: list[EntradaDirectorio] = []
    try:
        entradas = list(destino.iterdir())
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Sin permiso para leer {destino}",
        ) from None

    for entrada in entradas:
        if entrada.name.startswith("."):
            continue
        try:
            if not entrada.is_dir():
                continue
        except OSError:
            # Enlaces rotos o unidades desconectadas: se saltan en vez de reventar
            # el listado entero.
            continue
        directorios.append(EntradaDirectorio(nombre=entrada.name, ruta=str(entrada)))

    directorios.sort(key=lambda item: item.nombre.lower())

    # En la raíz de una unidad, `parent` devuelve la propia raíz: eso significa que
    # ya no se puede subir más.
    padre = destino.parent
    return ListadoDirectorio(
        ruta=str(destino),
        padre=None if padre == destino else str(padre),
        directorios=directorios,
    )

"""DTOs del explorador de disco que alimenta el selector de carpetas."""

from pydantic import BaseModel


class EntradaDirectorio(BaseModel):
    """Un subdirectorio del listado.

    `accesible` en `False` significa que la carpeta existe pero no se puede abrir
    desde este equipo: es el caso de las *junctions* de un recurso compartido que
    apuntan fuera de él. Se listan igualmente, en vez de ocultarlas, para que se vea
    que están ahí y por qué no se pueden usar.
    """

    nombre: str
    ruta: str
    accesible: bool = True
    motivo: str | None = None


class ListadoDirectorio(BaseModel):
    """Contenido (solo directorios) de una ruta, con su padre para poder subir."""

    ruta: str
    padre: str | None
    directorios: list[EntradaDirectorio]

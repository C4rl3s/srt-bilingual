"""DTOs del explorador de disco que alimenta el selector de carpetas."""

from pydantic import BaseModel


class EntradaDirectorio(BaseModel):
    """Un subdirectorio navegable."""

    nombre: str
    ruta: str


class ListadoDirectorio(BaseModel):
    """Contenido (solo directorios) de una ruta, con su padre para poder subir."""

    ruta: str
    padre: str | None
    directorios: list[EntradaDirectorio]

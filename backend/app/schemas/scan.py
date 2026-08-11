"""DTOs del escaneo de carpetas."""

from pydantic import BaseModel


class PeticionEscaneo(BaseModel):
    """Qué carpetas escanear. Sin `carpeta_ids` se escanean todas las activas."""

    carpeta_ids: list[int] | None = None


class ResumenEscaneo(BaseModel):
    """Resultado agregado de un escaneo (`POST /scan`).

    `nuevos`, `actualizados` y `sin_cambios` particionan los ficheros vistos
    (`total`). `traducidos` y `errores` son subconjuntos según el estado final.
    """

    carpetas: int = 0
    nuevos: int = 0
    actualizados: int = 0
    sin_cambios: int = 0
    traducidos: int = 0
    errores: int = 0
    huerfanos_borrados: int = 0
    total: int = 0

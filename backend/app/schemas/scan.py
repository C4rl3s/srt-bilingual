"""DTOs del escaneo de carpetas."""

from pydantic import BaseModel


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

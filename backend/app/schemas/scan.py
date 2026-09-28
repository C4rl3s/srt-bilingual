"""DTOs del escaneo de carpetas."""

from pydantic import BaseModel, ConfigDict


class PeticionEscaneo(BaseModel):
    """Qué carpetas escanear. Sin `carpeta_ids` se escanean todas las activas."""

    carpeta_ids: list[int] | None = None


class ResumenEscaneo(BaseModel):
    """Resultado agregado de un escaneo (`POST /scan`).

    Todos los contadores salvo `carpetas` y `videos` hablan de **subtítulos**:
    `nuevos`, `actualizados` y `sin_cambios` particionan los `.srt` vistos
    (`total`), y `traducidos` y `errores` son subconjuntos según el estado final.
    `videos` cuenta los contenedores inventariados, que no se parsean.
    """

    carpetas: int = 0
    videos: int = 0
    nuevos: int = 0
    actualizados: int = 0
    sin_cambios: int = 0
    traducidos: int = 0
    errores: int = 0
    huerfanos_borrados: int = 0
    total: int = 0


class ProgresoSondeoOut(BaseModel):
    """Progreso del sondeo de pistas que sigue a cada escaneo (`GET /scan/sondeo`).

    `hechos` de `total` vídeos; `errores`, los que `ffprobe` no pudo leer (se
    reintentan en el próximo escaneo), con el mensaje del último.
    """

    model_config = ConfigDict(from_attributes=True)

    en_curso: bool
    hechos: int
    total: int
    errores: int
    ultimo_error: str | None

"""DTOs de las carpetas vigiladas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CarpetaCrear(BaseModel):
    """Alta de una carpeta: solo la ruta, el resto lo decide el servidor."""

    ruta: str


class CarpetaActualizar(BaseModel):
    """Cambio de la casilla de inclusión en el escaneo."""

    activa: bool


class CarpetaOut(BaseModel):
    """Carpeta con sus contadores, tal como la pinta el panel del frontend.

    Los contadores no son columnas: se calculan al consultar, agrupando sus
    subtítulos por estado.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    ruta: str
    activa: bool
    ultimo_escaneo: datetime | None
    num_subtitulos: int = 0
    num_dual: int = 0
    num_pendientes: int = 0
    num_errores: int = 0

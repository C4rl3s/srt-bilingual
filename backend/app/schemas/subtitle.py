"""DTOs de salida de los subtítulos."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import EstadoSubtitulo, FormatoSubtitulo, Idioma


class SubtituloOut(BaseModel):
    """Representación de un subtítulo para la API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    ruta: str
    nombre: str
    formato: FormatoSubtitulo
    idioma_origen: Idioma
    num_caracteres: int
    num_bloques: int
    estado: EstadoSubtitulo
    ruta_bilingue: str | None
    idioma_destino: Idioma | None
    proveedor: str | None
    mensaje_error: str | None
    actualizado_en: datetime

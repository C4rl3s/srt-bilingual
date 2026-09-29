"""DTOs de la generación de bilingües: peticiones, trabajos y candidatos de origen."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EstadoTrabajo, FaseTrabajo, FormatoSubtitulo, Idioma, ModoTrabajo
from app.services.subtitles.seleccion import MotivoDescarte


class PeticionTraduccion(BaseModel):
    """Qué orígenes convertir en bilingüe (`POST /translate`)."""

    subtitulo_ids: list[int] = Field(min_length=1)
    # Traducir aunque la obra tenga coreano: el camino cuando la fusión sale mala.
    forzar_traduccion: bool = False
    # Proveedor concreto; sin él, el de `TRANSLATION_PROVIDER`.
    proveedor: str | None = None


class TrabajoOut(BaseModel):
    """Un trabajo y su progreso, tal como lo sondea el frontend."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    modo: ModoTrabajo
    estado: EstadoTrabajo
    fase: FaseTrabajo | None
    activo: bool
    subtitulo_id: int | None
    subtitulo_coreano_id: int | None
    ruta_origen: str
    ruta_bilingue: str | None
    idioma_origen: Idioma
    proveedor: str | None
    # La guía de la serie con que se tradujo, si el proveedor la usó.
    guia: str | None
    num_caracteres: int
    caracteres_previstos: int
    calidad_alineacion: float | None
    bloques_totales: int
    bloques_procesados: int
    mensaje_error: str | None
    creado_en: datetime
    iniciado_en: datetime | None
    finalizado_en: datetime | None


class RechazoOut(BaseModel):
    subtitulo_id: int
    motivo: str


class RespuestaTraduccion(BaseModel):
    """Lo encolado y lo rechazado: una petición con varios orígenes no falla entera
    porque uno no sirva."""

    trabajos: list[TrabajoOut]
    rechazados: list[RechazoOut]


class CandidatoOut(BaseModel):
    """Un subtítulo de la obra y si sirve (o por qué no) como origen o coreano."""

    subtitulo_id: int
    nombre: str
    ruta: str
    idioma: Idioma
    num_bloques: int
    es_forzado: bool
    es_sdh: bool
    descarte: MotivoDescarte | None
    formato: FormatoSubtitulo
    # Pista incrustada en el vídeo (Fase 5): su índice y su título en el contenedor.
    es_pista: bool
    indice_pista: int | None
    titulo_pista: str | None
    # `False` si `num_bloques` sale de la cabecera de la pista (o es 0 = no se sabe).
    metricas_exactas: bool


class MuestraOut(BaseModel):
    """Un bloque de ejemplo de cómo quedará el bilingüe."""

    tiempo: str  # HH:MM:SS,mmm
    origen: str
    coreano: str | None  # vacío si el coreano saldrá de traducir


class EstadoCupoOut(BaseModel):
    """El cupo de un proveedor configurado (`GET /translate/cupos`)."""

    model_config = ConfigDict(from_attributes=True)

    proveedor: str
    disponible: bool
    motivo: str | None
    # API: lo dice el proveedor · REGISTRO: suma de lo enviado por la app este mes.
    fuente: str
    usados: int
    reservados: int
    limite: int | None
    libre: int | None
    # Si aprovecha la guía de la serie; con guía se le prefiere (`eleccion.py`).
    admite_guia: bool


class GuiaOut(BaseModel):
    """La guía de traducción que le toca a la obra, resumida para el panel."""

    ruta: str
    # Carpeta donde está (la de la serie o la temporada), para mostrarla corta.
    carpeta: str
    terminos: int
    instrucciones: int
    # Si no se puede usar: el motivo (TOML roto, borrada desde el escaneo…).
    error: str | None = None


class CandidatosOut(BaseModel):
    """La obra de un subtítulo: qué origen y qué coreano se proponen, y todo lo demás
    con su motivo, para que la interfaz deje elegir otro."""

    obra: str
    # La guía de la serie según el índice del escaneo, leída del disco (ver
    # `services/translation/guia.py`). La misma que decide la previsión de proveedor.
    guia: GuiaOut | None = None
    muestra: list[MuestraOut]
    origen_id: int | None
    coreano_id: int | None
    # Solo si hay origen y coreano: cómo de bien casan, calculado al vuelo sin gastar
    # cuota. Si no es aceptable, la interfaz debe ofrecer traducir.
    calidad_alineacion: float | None
    fusion_aceptable: bool | None
    candidatos: list[CandidatoOut]
    # Si el origen o el coreano son pistas sin extraer, no hay muestra ni calidad
    # hasta extraerlas (`POST /videos/{video_id}/extraer`).
    extraccion_pendiente: bool = False
    video_id: int | None = None
    extrayendo: bool = False
    error_extraccion: str | None = None


class ExtraccionOut(BaseModel):
    """Respuesta de `POST /videos/{id}/extraer`."""

    video_id: int
    en_curso: bool
    error: str | None


class PropuestaRenombradoOut(BaseModel):
    subtitulo_id: int
    ruta_actual: str
    ruta_nueva: str
    conflicto: str | None


class PeticionRenombrado(BaseModel):
    subtitulo_ids: list[int] = Field(min_length=1)


class ResultadoRenombradoOut(BaseModel):
    renombrados: list[PropuestaRenombradoOut]
    rechazados: list[PropuestaRenombradoOut]

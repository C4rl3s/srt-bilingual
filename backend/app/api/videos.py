"""Router de los vídeos: extraer sus pistas de subtítulo incrustadas (Fase 5)."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.translate import get_fabrica_sesion
from app.db import get_db
from app.models.media_file import ArchivoMedia
from app.schemas.trabajo import ExtraccionOut
from app.services import trabajos
from app.services.mkv import extraccion
from app.services.subtitles.lectura import esta_extraida

router = APIRouter(tags=["videos"])


# Dependencia de la tarea de fondo, para que los tests pongan un ffmpeg de pega.
def get_extractor() -> extraccion.Extractor:
    return extraccion.ejecutar_ffmpeg


@router.post(
    "/videos/{video_id}/extraer",
    response_model=ExtraccionOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def extraer_pistas(
    video_id: int,
    tareas: BackgroundTasks,
    db: Session = Depends(get_db),
    fabrica_sesion: trabajos.FabricaSesion = Depends(get_fabrica_sesion),
    extractor: extraccion.Extractor = Depends(get_extractor),
) -> ExtraccionOut:
    """Extrae en segundo plano las pistas de texto del vídeo, para ver la muestra y la
    calidad de la fusión antes de generar. Lee el vídeo entero: por la red, 1–1,5 min
    por episodio. Si ya estaba todo en la caché, no hace nada.

    El estado se consulta en los candidatos de cualquier subtítulo de su obra.
    """
    video = db.get(ArchivoMedia, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Vídeo no encontrado")
    if not extraccion.extraibles(video):
        raise HTTPException(status_code=409, detail="El vídeo no tiene pistas de texto que extraer")

    if all(esta_extraida(p) for p in extraccion.extraibles(video)):
        return ExtraccionOut(video_id=video_id, en_curso=False, error=None)
    extraccion.marcar_pedida(video_id)
    tareas.add_task(extraccion.extraer_en_segundo_plano, video_id, fabrica_sesion, extractor)
    return ExtraccionOut(video_id=video_id, en_curso=True, error=None)

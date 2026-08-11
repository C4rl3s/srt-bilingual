"""Router de consulta de subtítulos."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.enums import EstadoSubtitulo, Idioma
from app.models.subtitle_file import ArchivoSubtitulo
from app.schemas.subtitle import SubtituloOut

router = APIRouter(tags=["subtitles"])


@router.get("/subtitles", response_model=list[SubtituloOut])
def listar_subtitulos(
    db: Session = Depends(get_db),
    estado: EstadoSubtitulo | None = Query(default=None),
    idioma: Idioma | None = Query(default=None),
) -> list[ArchivoSubtitulo]:
    """Lista los subtítulos inventariados, con filtros opcionales por estado e idioma."""
    consulta = select(ArchivoSubtitulo)
    if estado is not None:
        consulta = consulta.where(ArchivoSubtitulo.estado == estado)
    if idioma is not None:
        consulta = consulta.where(ArchivoSubtitulo.idioma_origen == idioma)
    consulta = consulta.order_by(ArchivoSubtitulo.ruta)
    return list(db.scalars(consulta).all())


@router.get("/subtitles/{subtitulo_id}", response_model=SubtituloOut)
def obtener_subtitulo(subtitulo_id: int, db: Session = Depends(get_db)) -> ArchivoSubtitulo:
    """Devuelve un subtítulo por id, o 404 si no existe."""
    sub = db.get(ArchivoSubtitulo, subtitulo_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Subtítulo no encontrado")
    return sub

"""Router del renombrado a la nomenclatura de Plex: primero proponer, luego aplicar.

Va en `/renombrado` y no en `/subtitles/renombrado`, como decía el plan: esa ruta
chocaría con `/subtitles/{subtitulo_id}`, que la capturaría antes y respondería 422
al no poder leer `renombrado` como número.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.trabajo import (
    PeticionRenombrado,
    PropuestaRenombradoOut,
    ResultadoRenombradoOut,
)
from app.services.subtitles import renombrado
from app.services.subtitles.renombrado import Propuesta

router = APIRouter(tags=["renombrado"])


def _out(propuesta: Propuesta) -> PropuestaRenombradoOut:
    return PropuestaRenombradoOut(
        subtitulo_id=propuesta.subtitulo_id,
        ruta_actual=str(propuesta.ruta_actual),
        ruta_nueva=str(propuesta.ruta_nueva),
        conflicto=propuesta.conflicto.value if propuesta.conflicto else None,
    )


@router.get("/renombrado/propuestas", response_model=list[PropuestaRenombradoOut])
def propuestas(
    db: Session = Depends(get_db),
    carpeta_id: list[int] | None = Query(default=None),
) -> list[PropuestaRenombradoOut]:
    """Lista `actual → nuevo`. No toca el disco."""
    return [_out(p) for p in renombrado.proponer(db, carpeta_ids=carpeta_id)]


@router.post("/renombrado", response_model=ResultadoRenombradoOut)
def aplicar(peticion: PeticionRenombrado, db: Session = Depends(get_db)) -> ResultadoRenombradoOut:
    """Renombra los subtítulos confirmados. Nunca sobrescribe un fichero existente."""
    resultado = renombrado.aplicar(db, peticion.subtitulo_ids)
    return ResultadoRenombradoOut(
        renombrados=[_out(p) for p in resultado.renombrados],
        rechazados=[_out(p) for p in resultado.rechazados],
    )

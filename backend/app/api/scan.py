"""Router de escaneo de carpetas."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.scan import PeticionEscaneo, ResumenEscaneo
from app.services import scanner

router = APIRouter(tags=["scan"])


@router.post("/scan", response_model=ResumenEscaneo)
def escanear_carpetas(
    peticion: PeticionEscaneo | None = None, db: Session = Depends(get_db)
) -> ResumenEscaneo:
    """Escanea las carpetas indicadas; sin cuerpo, todas las marcadas como activas."""
    carpeta_ids = peticion.carpeta_ids if peticion is not None else None
    return scanner.escanear(db, carpeta_ids=carpeta_ids)

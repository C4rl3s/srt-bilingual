"""Router de escaneo de carpetas."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.scan import ResumenEscaneo
from app.services import scanner

router = APIRouter(tags=["scan"])


@router.post("/scan", response_model=ResumenEscaneo)
def escanear_carpetas(db: Session = Depends(get_db)) -> ResumenEscaneo:
    """Recorre las carpetas configuradas y actualiza el inventario de subtítulos."""
    return scanner.escanear(db)

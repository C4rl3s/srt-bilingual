"""Router de escaneo de carpetas y del sondeo de pistas que lo sigue."""

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.api.translate import get_fabrica_sesion
from app.db import get_db
from app.schemas.scan import PeticionEscaneo, ProgresoSondeoOut, ResumenEscaneo
from app.services import scanner
from app.services.mkv import sondeo

router = APIRouter(tags=["scan"])


# Dependencia de la tarea de fondo, para que los tests pongan un ffprobe de pega.
def get_sondeador() -> sondeo.Sondeador:
    return sondeo.ejecutar_ffprobe


@router.post("/scan", response_model=ResumenEscaneo)
def escanear_carpetas(
    tareas: BackgroundTasks,
    peticion: PeticionEscaneo | None = None,
    db: Session = Depends(get_db),
    fabrica_sesion: sondeo.FabricaSesion = Depends(get_fabrica_sesion),
    sondeador: sondeo.Sondeador = Depends(get_sondeador),
) -> ResumenEscaneo:
    """Escanea las carpetas indicadas; sin cuerpo, todas las marcadas como activas.

    Responde en cuanto termina el inventario. El sondeo de las pistas de los vídeos
    nuevos o cambiados sigue en segundo plano (`GET /scan/sondeo`).
    """
    carpeta_ids = peticion.carpeta_ids if peticion is not None else None
    resumen = scanner.escanear(db, carpeta_ids=carpeta_ids)
    tareas.add_task(sondeo.sondear_pendientes, fabrica_sesion, sondeador)
    return resumen


@router.get("/scan/sondeo", response_model=ProgresoSondeoOut)
def progreso_sondeo() -> ProgresoSondeoOut:
    """Cómo va el sondeo de pistas en curso (o cómo acabó el último)."""
    return ProgresoSondeoOut.model_validate(sondeo.progreso())

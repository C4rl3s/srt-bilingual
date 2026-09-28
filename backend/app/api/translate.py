"""Router de generación de bilingües: encolar, consultar trabajos y ver candidatos."""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_db
from app.models.enums import EstadoTrabajo
from app.models.subtitle_file import ArchivoSubtitulo
from app.models.translation_job import TrabajoTraduccion
from app.schemas.trabajo import (
    CandidatoOut,
    CandidatosOut,
    PeticionTraduccion,
    RechazoOut,
    RespuestaTraduccion,
    TrabajoOut,
)
from app.services import trabajos
from app.services.obras import obra_de
from app.services.subtitles.alineacion import alinear
from app.services.subtitles.seleccion import seleccionar
from app.services.subtitles.srt_parser import parsear
from app.services.translation.registry import obtener_traductor

router = APIRouter(tags=["translate"])


# Dependencias de la tarea de fondo. Existen para que los tests las sustituyan: una
# sesión contra la BD de pruebas y un traductor falso que no llama a DeepL.
def get_fabrica_sesion() -> trabajos.FabricaSesion:
    return SessionLocal


def get_fabrica_traductor() -> trabajos.FabricaTraductor:
    return obtener_traductor


@router.post("/translate", response_model=RespuestaTraduccion, status_code=status.HTTP_202_ACCEPTED)
def traducir(
    peticion: PeticionTraduccion,
    tareas: BackgroundTasks,
    db: Session = Depends(get_db),
    fabrica_sesion: trabajos.FabricaSesion = Depends(get_fabrica_sesion),
    fabrica_traductor: trabajos.FabricaTraductor = Depends(get_fabrica_traductor),
) -> RespuestaTraduccion:
    """Encola la generación del bilingüe de cada origen y responde sin esperar.

    `202 Accepted`: el trabajo queda aceptado, no hecho. El progreso se consulta en
    `GET /translate/jobs/{id}`.
    """
    creados, rechazos = trabajos.crear(
        db, peticion.subtitulo_ids, peticion.forzar_traduccion, peticion.proveedor
    )
    for trabajo in creados:
        if trabajo.estado is EstadoTrabajo.QUEUED:
            tareas.add_task(trabajos.ejecutar, trabajo.id, fabrica_sesion, fabrica_traductor)
    return RespuestaTraduccion(
        trabajos=[TrabajoOut.model_validate(t) for t in creados],
        rechazados=[RechazoOut(subtitulo_id=r.subtitulo_id, motivo=r.motivo) for r in rechazos],
    )


@router.get("/translate/jobs", response_model=list[TrabajoOut])
def listar_trabajos(
    db: Session = Depends(get_db),
    estado: EstadoTrabajo | None = Query(default=None),
    activos: bool = Query(default=False, description="Solo los que aún no han terminado"),
) -> list[TrabajoTraduccion]:
    """Trabajos, del más reciente al más antiguo."""
    consulta = select(TrabajoTraduccion).order_by(TrabajoTraduccion.id.desc())
    if estado is not None:
        consulta = consulta.where(TrabajoTraduccion.estado == estado)
    if activos:
        consulta = consulta.where(
            TrabajoTraduccion.estado.in_([EstadoTrabajo.QUEUED, EstadoTrabajo.RUNNING])
        )
    return list(db.scalars(consulta).all())


@router.get("/translate/jobs/{trabajo_id}", response_model=TrabajoOut)
def obtener_trabajo(trabajo_id: int, db: Session = Depends(get_db)) -> TrabajoTraduccion:
    trabajo = db.get(TrabajoTraduccion, trabajo_id)
    if trabajo is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    return trabajo


@router.get("/subtitles/{subtitulo_id}/candidatos", response_model=CandidatosOut)
def candidatos(subtitulo_id: int, db: Session = Depends(get_db)) -> CandidatosOut:
    """Los subtítulos de la obra de `subtitulo_id`, con la propuesta de origen y
    coreano y el motivo de cada descarte.

    Si hay origen y coreano, calcula al vuelo cómo de bien casan (lee los dos
    ficheros, no gasta cuota): así la interfaz sabe, antes de lanzar nada, si la
    fusión saldrá bien o conviene traducir.
    """
    sub = db.get(ArchivoSubtitulo, subtitulo_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Subtítulo no encontrado")
    obra = obra_de(sub)
    seleccion = seleccionar(obra.subtitulos)

    calidad = aceptable = None
    if seleccion.origen and seleccion.coreano:
        resultado = alinear(
            parsear(Path(seleccion.origen.ruta)), parsear(Path(seleccion.coreano.ruta))
        )
        calidad, aceptable = round(resultado.calidad, 3), resultado.aceptable

    return CandidatosOut(
        obra=obra.nombre,
        origen_id=seleccion.origen.id if seleccion.origen else None,
        coreano_id=seleccion.coreano.id if seleccion.coreano else None,
        calidad_alineacion=calidad,
        fusion_aceptable=aceptable,
        candidatos=[
            CandidatoOut(
                subtitulo_id=c.subtitulo.id,
                nombre=c.subtitulo.nombre,
                ruta=c.subtitulo.ruta,
                idioma=c.subtitulo.idioma_origen,
                num_bloques=c.subtitulo.num_bloques,
                es_forzado=c.subtitulo.es_forzado,
                es_sdh=c.subtitulo.es_sdh,
                descarte=c.descarte,
            )
            for c in seleccion.candidatos
        ],
    )

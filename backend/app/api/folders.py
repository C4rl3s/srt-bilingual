"""Router de gestión de las carpetas vigiladas.

Sustituye a la antigua variable `MEDIA_FOLDERS`: la tabla `library_folder` es ahora
la única autoridad sobre qué se escanea, y se administra desde la interfaz.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.enums import EstadoSubtitulo
from app.models.library_folder import CarpetaBiblioteca
from app.models.subtitle_file import ArchivoSubtitulo
from app.schemas.folder import CarpetaActualizar, CarpetaCrear, CarpetaOut

router = APIRouter(tags=["folders"])


@router.get("/folders", response_model=list[CarpetaOut])
def listar_carpetas(db: Session = Depends(get_db)) -> list[CarpetaOut]:
    """Carpetas vigiladas con sus contadores por estado."""
    # Un único GROUP BY con contadores condicionales evita una consulta por carpeta.
    # `count(...).filter(...)` genera la cláusula FILTER de SQL, que cuenta solo las
    # filas del grupo que cumplen la condición.
    conteos = (
        select(
            ArchivoSubtitulo.carpeta_id,
            func.count(ArchivoSubtitulo.id).label("total"),
            func.count(ArchivoSubtitulo.id)
            .filter(ArchivoSubtitulo.estado == EstadoSubtitulo.TRANSLATED)
            .label("dual"),
            func.count(ArchivoSubtitulo.id)
            .filter(ArchivoSubtitulo.estado == EstadoSubtitulo.PENDING)
            .label("pendientes"),
            func.count(ArchivoSubtitulo.id)
            .filter(ArchivoSubtitulo.estado == EstadoSubtitulo.ERROR)
            .label("errores"),
        )
        .group_by(ArchivoSubtitulo.carpeta_id)
        .subquery()
    )

    filas = db.execute(
        select(
            CarpetaBiblioteca,
            conteos.c.total,
            conteos.c.dual,
            conteos.c.pendientes,
            conteos.c.errores,
        )
        .outerjoin(conteos, conteos.c.carpeta_id == CarpetaBiblioteca.id)
        .order_by(CarpetaBiblioteca.ruta)
    ).all()

    # El LEFT JOIN deja los contadores a NULL en las carpetas sin subtítulos.
    return [
        CarpetaOut(
            id=carpeta.id,
            ruta=carpeta.ruta,
            activa=carpeta.activa,
            ultimo_escaneo=carpeta.ultimo_escaneo,
            num_subtitulos=total or 0,
            num_dual=dual or 0,
            num_pendientes=pendientes or 0,
            num_errores=errores or 0,
        )
        for carpeta, total, dual, pendientes, errores in filas
    ]


@router.post("/folders", response_model=CarpetaOut, status_code=status.HTTP_201_CREATED)
def crear_carpeta(datos: CarpetaCrear, db: Session = Depends(get_db)) -> CarpetaOut:
    """Da de alta una carpeta, rechazando rutas inválidas y solapamientos."""
    ruta = Path(datos.ruta).expanduser()
    if not ruta.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La ruta no existe o no es una carpeta: {datos.ruta}",
        )
    ruta = ruta.resolve()

    for existente in db.scalars(select(CarpetaBiblioteca)).all():
        otra = Path(existente.ruta)
        if ruta == otra:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Esa carpeta ya está en la lista",
            )
        # El escaneo es recursivo: si una contiene a la otra, el mismo `.srt`
        # quedaría reclamado por dos carpetas y chocaría con el índice único de
        # `subtitle_file.ruta`.
        if ruta.is_relative_to(otra):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya se vigila una carpeta superior: {existente.ruta}",
            )
        if otra.is_relative_to(ruta):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya se vigila una subcarpeta suya: {existente.ruta}",
            )

    carpeta = CarpetaBiblioteca(ruta=str(ruta))
    db.add(carpeta)
    db.commit()
    return _a_dto(carpeta)


@router.patch("/folders/{carpeta_id}", response_model=CarpetaOut)
def actualizar_carpeta(
    carpeta_id: int, datos: CarpetaActualizar, db: Session = Depends(get_db)
) -> CarpetaOut:
    """Marca o desmarca la carpeta. Desmarcarla no borra sus subtítulos."""
    carpeta = _obtener(db, carpeta_id)
    carpeta.activa = datos.activa
    db.commit()
    return _a_dto(carpeta)


@router.delete("/folders/{carpeta_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_carpeta(carpeta_id: int, db: Session = Depends(get_db)) -> None:
    """Deja de vigilar la carpeta; la cascada se lleva sus subtítulos."""
    db.delete(_obtener(db, carpeta_id))
    db.commit()


def _obtener(db: Session, carpeta_id: int) -> CarpetaBiblioteca:
    carpeta = db.get(CarpetaBiblioteca, carpeta_id)
    if carpeta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Carpeta no encontrada")
    return carpeta


def _a_dto(carpeta: CarpetaBiblioteca) -> CarpetaOut:
    """DTO de una sola carpeta contando en Python sobre la relación ya cargada.

    Para una carpeta suelta no compensa repetir el GROUP BY del listado.
    """
    subs = carpeta.subtitulos
    return CarpetaOut(
        id=carpeta.id,
        ruta=carpeta.ruta,
        activa=carpeta.activa,
        ultimo_escaneo=carpeta.ultimo_escaneo,
        num_subtitulos=len(subs),
        num_dual=sum(1 for sub in subs if sub.estado is EstadoSubtitulo.TRANSLATED),
        num_pendientes=sum(1 for sub in subs if sub.estado is EstadoSubtitulo.PENDING),
        num_errores=sum(1 for sub in subs if sub.estado is EstadoSubtitulo.ERROR),
    )

"""Router de generación de bilingües: encolar, consultar trabajos y ver candidatos."""

from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.api.dependencias import get_extractor, get_fabrica_sesion, get_fabrica_traductor
from app.db import get_db
from app.models.enums import EstadoTrabajo
from app.models.library_folder import CarpetaBiblioteca
from app.models.subtitle_file import ArchivoSubtitulo
from app.models.translation_job import TrabajoTraduccion
from app.schemas.trabajo import (
    CandidatoOut,
    CandidatosOut,
    EstadoCupoOut,
    GuiaOut,
    MuestraOut,
    PeticionTraduccion,
    RechazoOut,
    RespuestaTraduccion,
    TrabajoOut,
)
from app.services import trabajos
from app.services.obras import Obra, obra_de
from app.services.subtitles.alineacion import alinear
from app.services.subtitles.modelo import Bloque
from app.services.mkv import extraccion
from app.services.subtitles.lectura import esta_extraida, leer_bloques
from app.services.subtitles.seleccion import seleccionar
from app.services.translation import consumo, registry
from app.services.translation.guia import GuiaInvalida
from app.services.translation.guia import buscar as buscar_guia
from app.services.translation.guia import leer as leer_guia

router = APIRouter(tags=["translate"])


@router.post("/translate", response_model=RespuestaTraduccion, status_code=status.HTTP_202_ACCEPTED)
def traducir(
    peticion: PeticionTraduccion,
    tareas: BackgroundTasks,
    db: Session = Depends(get_db),
    fabrica_sesion: trabajos.FabricaSesion = Depends(get_fabrica_sesion),
    fabrica_traductor: trabajos.FabricaTraductor = Depends(get_fabrica_traductor),
    extractor: extraccion.Extractor = Depends(get_extractor),
) -> RespuestaTraduccion:
    """Encola la generación del bilingüe de cada origen y responde sin esperar.

    `202 Accepted`: el trabajo queda aceptado, no hecho. El progreso se consulta en
    `GET /translate/jobs/{id}`.
    """
    creados, rechazos = trabajos.crear(
        db,
        peticion.subtitulo_ids,
        peticion.forzar_traduccion,
        peticion.proveedor,
        estados_cupo=lambda: consumo.estados(
            db, settings.proveedores, fabrica_traductor, registry.limite_configurado
        ),
    )
    for trabajo in creados:
        if trabajo.estado is EstadoTrabajo.QUEUED:
            tareas.add_task(
                trabajos.ejecutar, trabajo.id, fabrica_sesion, fabrica_traductor, extractor
            )
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


@router.get("/translate/cupos", response_model=list[EstadoCupoOut])
def cupos(
    db: Session = Depends(get_db),
    fabrica_traductor: trabajos.FabricaTraductor = Depends(get_fabrica_traductor),
) -> list[EstadoCupoOut]:
    """El cupo de cada proveedor configurado, en su orden de preferencia: usados,
    reservados por trabajos en marcha, límite, libre y de dónde sale la cifra.

    Nunca falla por un proveedor: sin clave, sin red o desconocido, sale con
    `disponible: false` y su motivo. La cabecera del frontend lo pide en cada carga.
    Sustituye al `GET /translate/cupo` de la Fase 3, que solo veía un proveedor.
    """
    return [
        EstadoCupoOut.model_validate(e)
        for e in consumo.estados(
            db, settings.proveedores, fabrica_traductor, registry.limite_configurado
        )
    ]


# Bloques de la muestra: dos bastan para ver cómo quedará. Se saltan los primeros,
# donde suelen ir los créditos del subtitulador o la publicidad de YTS.
TAMANO_MUESTRA = 2
BLOQUES_INICIALES_SALTADOS = 2


def _muestra(bloques: list[Bloque], textos_coreano: list[str] | None) -> list[MuestraOut]:
    """Unos bloques reales del origen y, si hay fusión, su coreano ya alineado.

    En modo traducción el coreano va vacío: traducir la muestra gastaría cupo.
    """
    muestra: list[MuestraOut] = []
    for i, bloque in enumerate(bloques[BLOQUES_INICIALES_SALTADOS:], BLOQUES_INICIALES_SALTADOS):
        coreano = textos_coreano[i] if textos_coreano else None
        if len(bloque.contenido) < 15 or (textos_coreano and not coreano):
            continue
        muestra.append(
            MuestraOut(tiempo=_marca(bloque.inicio), origen=bloque.contenido, coreano=coreano)
        )
        if len(muestra) == TAMANO_MUESTRA:
            break
    return muestra


def _marca(instante: timedelta) -> str:
    """`timedelta` → `HH:MM:SS,mmm`, como en el `.srt`."""
    ms = round(instante.total_seconds() * 1000)
    return f"{ms // 3_600_000:02d}:{ms // 60_000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def _guia(obra: Obra, carpeta: CarpetaBiblioteca) -> GuiaOut | None:
    """La guía de la obra para el panel.

    Se localiza con el **índice** del escaneo, como en el árbol, para que el panel
    diga lo mismo que la previsión de proveedor; su contenido se lee del disco. Una
    guía que ya no está, o que no se puede leer, sale con su motivo.
    """
    indice = {guia.ruta for guia in carpeta.guias}
    ruta = buscar_guia(obra.directorio, Path(carpeta.ruta), existe=lambda p: str(p) in indice)
    if ruta is None:
        return None
    resumen = GuiaOut(ruta=str(ruta), carpeta=ruta.parent.name, terminos=0, instrucciones=0)
    if not ruta.is_file():
        resumen.error = "Ya no está en disco: vuelve a escanear"
        return resumen
    try:
        guia = leer_guia(ruta)
    except GuiaInvalida as exc:
        resumen.error = str(exc)
        return resumen
    resumen.terminos = len(guia.glosario)
    resumen.instrucciones = len(guia.instrucciones)
    return resumen


@router.get("/subtitles/{subtitulo_id}/candidatos", response_model=CandidatosOut)
def candidatos(
    subtitulo_id: int,
    db: Session = Depends(get_db),
    origen_id: int | None = Query(default=None, description="Origen elegido a mano"),
) -> CandidatosOut:
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
    seleccion = seleccionar(obra.subtitulos, origen_preferido_id=origen_id)

    calidad = aceptable = None
    muestra: list[MuestraOut] = []
    # Una pista sin extraer no se puede leer aquí: costaría leer el MKV entero por la
    # red en mitad de una petición. Sin muestra ni calidad hasta que se extraiga.
    elegidos = [s for s in (seleccion.origen, seleccion.coreano) if s is not None]
    sin_extraer = [s for s in elegidos if not esta_extraida(s)]
    if seleccion.origen and not sin_extraer:
        bloques_origen = leer_bloques(seleccion.origen)
        textos_coreano = None
        if seleccion.coreano:
            resultado = alinear(bloques_origen, leer_bloques(seleccion.coreano))
            calidad, aceptable = round(resultado.calidad, 3), resultado.aceptable
            textos_coreano = resultado.textos
        muestra = _muestra(bloques_origen, textos_coreano)

    # Las pistas de una obra son todas del mismo vídeo: con una basta para saber cuál.
    video_id = sin_extraer[0].video_id if sin_extraer else None
    estado_extraccion = extraccion.estado(video_id) if video_id is not None else None

    return CandidatosOut(
        guia=_guia(obra, sub.carpeta),
        extraccion_pendiente=bool(sin_extraer),
        video_id=video_id,
        extrayendo=bool(estado_extraccion and estado_extraccion.en_curso),
        error_extraccion=estado_extraccion.error if estado_extraccion else None,
        muestra=muestra,
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
                formato=c.subtitulo.formato,
                es_pista=c.subtitulo.es_pista,
                indice_pista=c.subtitulo.indice_pista,
                titulo_pista=c.subtitulo.titulo_pista,
                metricas_exactas=c.subtitulo.metricas_exactas,
            )
            for c in seleccion.candidatos
        ],
    )

"""Trabajos de generación de bilingües: se crean al pedirlos y se ejecutan en segundo
plano (`BackgroundTasks` de FastAPI, sin Celery).

Crear es rápido: valida, decide el modo, elige el proveedor según su cupo (como mucho
una consulta de cupo por petición) y deja el trabajo en `QUEUED`. Ejecutar es lo lento (leer de la red, traducir o alinear, escribir) y
va aparte, con **su propia sesión de base de datos**: la que inyecta `get_db` se
cierra en cuanto la petición HTTP responde, antes de que empiece la tarea de fondo.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import EstadoSubtitulo, EstadoTrabajo, Idioma, ModoTrabajo
from app.models.subtitle_file import ArchivoSubtitulo
from app.models.translation_job import TrabajoTraduccion
from app.services import bilingual
from app.services.obras import obra_de, ruta_bilingue
from app.services.subtitles.alineacion import UMBRAL_CALIDAD, alinear
from app.services.subtitles.seleccion import IDIOMA_DESTINO, IDIOMAS_ORIGEN, seleccionar
from app.services.subtitles.srt_parser import parsear
from app.config import settings
from app.services.translation import consumo, registry
from app.services.translation.base import ErrorTraduccion, Translator
from app.services.translation.consumo import EstadoCupo
from app.services.translation.eleccion import Asignador
from app.services.translation.registry import obtener_traductor

# Bloques que se traducen entre dos actualizaciones del progreso. El proveedor
# agrupa por su cuenta como le convenga; esto solo marca el ritmo de la barra.
BLOQUES_POR_PASO = 50

type FabricaSesion = Callable[[], Session]
type FabricaTraductor = Callable[[str | None], Translator]


def _ahora() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Rechazo:
    """Un subtítulo pedido que no se ha encolado, y por qué."""

    subtitulo_id: int
    motivo: str


def crear(
    db: Session,
    subtitulo_ids: list[int],
    forzar_traduccion: bool = False,
    proveedor: str | None = None,
    estados_cupo: Callable[[], list[EstadoCupo]] | None = None,
) -> tuple[list[TrabajoTraduccion], list[Rechazo]]:
    """Crea (en `QUEUED`) un trabajo por cada origen pedido.

    El modo se decide solo: **fusión** si la obra tiene un coreano válido, y
    **traducción** si no, o si se pide `forzar_traduccion` (el camino para cuando
    la fusión sale de mala calidad). Si ya hay un trabajo activo para ese origen,
    se devuelve ese en vez de duplicarlo.

    Cada traducción recibe **proveedor según su cupo** (`eleccion.Asignador`), salvo
    que se pida uno concreto. Si ninguno llega, la obra va a los rechazos y no se
    crea el trabajo. `estados_cupo` da el cupo de cada proveedor en su orden de
    preferencia; solo se consulta si hay algo que traducir (preguntar a la API de
    DeepL cuesta una llamada de red, y una fusión no la necesita).
    """
    trabajos: list[TrabajoTraduccion] = []
    rechazos: list[Rechazo] = []
    asignador: Asignador | None = None

    for subtitulo_id in dict.fromkeys(subtitulo_ids):  # sin repetidos, en orden
        sub = db.get(ArchivoSubtitulo, subtitulo_id)
        if sub is None:
            rechazos.append(Rechazo(subtitulo_id, "No existe"))
            continue
        if sub.estado is EstadoSubtitulo.ERROR or sub.idioma_origen not in IDIOMAS_ORIGEN:
            rechazos.append(Rechazo(subtitulo_id, "No es un origen válido (ni español ni inglés)"))
            continue

        # TODO(Fase 5, hito 3): generar desde pistas incrustadas (extraer y leer).
        if sub.es_pista:
            rechazos.append(
                Rechazo(subtitulo_id, "Las pistas incrustadas aún no se pueden generar")
            )
            continue

        activo = _trabajo_activo(db, subtitulo_id)
        if activo is not None:
            trabajos.append(activo)
            continue

        obra = obra_de(sub)
        # `origen_preferido_id` hace de override: se respeta el origen pedido aunque
        # la heurística propusiera otro (p. ej. el inglés teniendo español).
        coreano = seleccionar(obra.subtitulos, origen_preferido_id=sub.id).coreano
        fusion = coreano is not None and not forzar_traduccion
        destino = ruta_bilingue(obra, Path(sub.carpeta.ruta), sub.idioma_origen, IDIOMA_DESTINO)

        elegido = proveedor
        if not fusion and elegido is None:
            if asignador is None:
                asignador = Asignador((estados_cupo or _estados_por_defecto(db))())
            elegido = asignador.asignar(sub.num_caracteres)
            if elegido is None:
                rechazos.append(Rechazo(subtitulo_id, asignador.motivo(sub.num_caracteres)))
                continue

        trabajo = TrabajoTraduccion(
            modo=ModoTrabajo.FUSION if fusion else ModoTrabajo.TRADUCCION,
            subtitulo_id=sub.id,
            subtitulo_coreano_id=coreano.id if fusion else None,
            ruta_origen=sub.ruta,
            ruta_coreano=coreano.ruta if fusion else None,
            ruta_bilingue=str(destino),
            idioma_origen=sub.idioma_origen,
            proveedor=None if fusion else elegido,
            # Una fusión no gasta cupo; una traducción, el texto de su origen.
            caracteres_previstos=0 if fusion else sub.num_caracteres,
            bloques_totales=sub.num_bloques,
        )
        db.add(trabajo)
        trabajos.append(trabajo)

    db.commit()
    return trabajos, rechazos


def _estados_por_defecto(db: Session) -> Callable[[], list[EstadoCupo]]:
    """El cupo de los proveedores configurados, con el registro real de proveedores."""
    return lambda: consumo.estados(
        db, settings.proveedores, obtener_traductor, registry.limite_configurado
    )


def _trabajo_activo(db: Session, subtitulo_id: int) -> TrabajoTraduccion | None:
    return db.scalars(
        select(TrabajoTraduccion).where(
            TrabajoTraduccion.subtitulo_id == subtitulo_id,
            TrabajoTraduccion.estado.in_([EstadoTrabajo.QUEUED, EstadoTrabajo.RUNNING]),
        )
    ).first()


def ejecutar(
    trabajo_id: int,
    fabrica_sesion: FabricaSesion,
    fabrica_traductor: FabricaTraductor = obtener_traductor,
) -> None:
    """Ejecuta un trabajo de principio a fin. Pensado para `BackgroundTasks`.

    Nunca deja escapar una excepción: cualquier fallo queda en el propio trabajo
    (`FAILED` + `mensaje_error`), que es donde el frontend lo va a buscar. Una tarea
    de fondo que revienta solo dejaría una traza en la consola del servidor.
    """
    with fabrica_sesion() as db:
        trabajo = db.get(TrabajoTraduccion, trabajo_id)
        if trabajo is None or trabajo.estado is not EstadoTrabajo.QUEUED:
            return
        trabajo.estado = EstadoTrabajo.RUNNING
        trabajo.iniciado_en = _ahora()
        db.commit()

        try:
            _generar(db, trabajo, fabrica_traductor)
        except Exception as exc:  # noqa: BLE001 — todo fallo acaba en el trabajo
            db.rollback()
            trabajo.estado = EstadoTrabajo.FAILED
            trabajo.mensaje_error = str(exc) or type(exc).__name__
        else:
            trabajo.estado = EstadoTrabajo.DONE
            _marcar_traducido(db, trabajo)
        trabajo.finalizado_en = _ahora()
        db.commit()


def _generar(db: Session, trabajo: TrabajoTraduccion, fabrica_traductor: FabricaTraductor) -> None:
    origen = parsear(Path(trabajo.ruta_origen))
    trabajo.bloques_totales = len(origen)

    if trabajo.modo is ModoTrabajo.FUSION:
        resultado = alinear(origen, parsear(Path(trabajo.ruta_coreano)))
        trabajo.calidad_alineacion = round(resultado.calidad, 3)
        if not resultado.aceptable:
            # No se traduce por su cuenta: gastar cuota lo decide el usuario.
            raise ErrorTraduccion(
                f"El coreano no casa con el origen (calidad {resultado.calidad:.2f}, "
                f"mínimo {UMBRAL_CALIDAD}); probablemente es de otra versión. "
                "Se puede pedir con forzar_traduccion."
            )
        textos = resultado.textos
        trabajo.bloques_procesados = len(origen)
    else:
        traductor = fabrica_traductor(trabajo.proveedor)
        trabajo.proveedor = traductor.nombre
        textos = _traducir_con_progreso(db, trabajo, traductor, [b.contenido for b in origen])

    bilingual.generar(origen, textos, Path(trabajo.ruta_bilingue))


def _traducir_con_progreso(
    db: Session, trabajo: TrabajoTraduccion, traductor: Translator, textos: list[str]
) -> list[str]:
    traducidos: list[str] = []
    for inicio in range(0, len(textos), BLOQUES_POR_PASO):
        paso = textos[inicio : inicio + BLOQUES_POR_PASO]
        resultado = traductor.traducir(paso, trabajo.idioma_origen, IDIOMA_DESTINO)
        # La invariante, comprobada también aquí: no se fía del proveedor.
        if len(resultado) != len(paso):
            raise ErrorTraduccion(f"{traductor.nombre} devolvió {len(resultado)} de {len(paso)}")
        traducidos += resultado
        # Lo enviado cuenta aunque luego el trabajo falle: el proveedor ya lo cobró.
        trabajo.num_caracteres += sum(len(t) for t in paso if t.strip())
        trabajo.bloques_procesados = len(traducidos)
        db.commit()
    return traducidos


def _marcar_traducido(db: Session, trabajo: TrabajoTraduccion) -> None:
    """Refleja el bilingüe en la fila del origen sin esperar al próximo escaneo."""
    sub = db.get(ArchivoSubtitulo, trabajo.subtitulo_id) if trabajo.subtitulo_id else None
    if sub is None:
        return
    sub.estado = EstadoSubtitulo.TRANSLATED
    sub.ruta_bilingue = trabajo.ruta_bilingue
    sub.idioma_destino = Idioma.KO
    sub.proveedor = trabajo.proveedor

"""Trabajos de generación de bilingües: se crean al pedirlos y se ejecutan en segundo
plano (`BackgroundTasks` de FastAPI, sin Celery).

Crear es rápido: valida, decide el modo, elige el proveedor según su cupo (como mucho
una consulta de cupo por petición) y deja el trabajo en `QUEUED`. Ejecutar es lo
lento (leer de la red, traducir o alinear, escribir) y va aparte, con **su propia
sesión de base de datos**: la que inyecta `get_db` se cierra en cuanto la petición
HTTP responde, antes de que empiece la tarea de fondo.

Si el origen o el coreano son **pistas incrustadas** (Fase 5), ejecutar empieza por
extraerlas del vídeo (fase `EXTRAYENDO`) y revisar lo elegido con el texto de verdad:
hasta entonces solo se conocía lo que decía la cabecera de la pista.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.enums import EstadoSubtitulo, EstadoTrabajo, FaseTrabajo, Idioma, ModoTrabajo
from app.models.subtitle_file import ArchivoSubtitulo
from app.models.translation_job import TrabajoTraduccion
from app.services import bilingual
from app.services.mkv import extraccion
from app.services.mkv.extraccion import Extractor, ejecutar_ffmpeg
from app.services.obras import obra_de, ruta_bilingue
from app.services.subtitles import lineas
from app.services.subtitles.alineacion import UMBRAL_CALIDAD, alinear
from app.services.subtitles.lectura import esta_extraida, leer_bloques
from app.services.subtitles.modelo import Bloque
from app.services.subtitles.seleccion import (
    IDIOMA_DESTINO,
    IDIOMAS_ORIGEN,
    MIN_BLOQUES,
    seleccionar,
)
from app.services.subtitles.srt_parser import parsear
from app.services.translation import consumo, registry
from app.services.translation.base import ErrorTraduccion, Translator
from app.services.translation.consumo import EstadoCupo
from app.services.translation.eleccion import MARGEN, Asignador
from app.services.translation.guia import Guia, GuiaInvalida, guia_de
from app.services.translation.registry import obtener_traductor

# Bloques que se traducen entre dos actualizaciones del progreso. El proveedor
# agrupa por su cuenta como le convenga; esto solo marca el ritmo de la barra.
BLOQUES_POR_PASO = 50

# Bloques de antes y de después que van como contexto si la guía lo pide. Dos por
# lado es lo que se probó en el S4 Pt. 1-07 (errores del 24 % al 12 %).
VECINOS_DE_CONTEXTO = 2

# Caracteres que se reservan para una pista sin extraer y sin estadísticas en su
# cabecera (el 5 % de las pistas de texto de la biblioteca). Por encima de la mediana
# de una película (34.000); un episodio de anime ronda los 10.000.
ESTIMACION_SIN_ESTADISTICAS = 40_000

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

    Cada traducción recibe **proveedor según su cupo** (`eleccion.Asignador`). Si se
    pide uno concreto (el usuario lo elige por obra), se usa ese, pero con la misma
    comprobación de clave y cupo. Si no llega, la obra va a los rechazos y no se
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

        elegido = None
        previstos = caracteres_previstos(sub)
        if not fusion:
            # La guía de la serie (del disco, que manda): si está rota, mejor decirlo
            # ahora que encolar un trabajo que fallaría al ejecutarse.
            try:
                con_guia = guia_de(obra.directorio, Path(sub.carpeta.ruta)) is not None
            except GuiaInvalida as exc:
                rechazos.append(Rechazo(subtitulo_id, str(exc)))
                continue
            if asignador is None:
                asignador = Asignador((estados_cupo or _estados_por_defecto(db))())
            # Un proveedor pedido pasa por la misma regla: si no tiene clave o no le
            # cabe, se rechaza aquí, antes de crear un trabajo que fallaría después.
            elegido = asignador.asignar(previstos, solo=proveedor, con_guia=con_guia)
            if elegido is None:
                rechazos.append(Rechazo(subtitulo_id, asignador.motivo(previstos, solo=proveedor)))
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
            caracteres_previstos=0 if fusion else previstos,
            bloques_totales=sub.num_bloques,
        )
        db.add(trabajo)
        trabajos.append(trabajo)

    db.commit()
    return trabajos, rechazos


def caracteres_previstos(sub: ArchivoSubtitulo) -> int:
    """Lo que costará traducir el subtítulo, para reservar cupo.

    En un `.srt` o una pista extraída, la cifra exacta. En una pista sin extraer, la
    cota superior de su cabecera (los bytes de la pista, ~el doble del texto) o, si
    no trae estadísticas, una estimación holgada. Al extraerla, el trabajo la corrige.
    """
    if sub.metricas_exactas or sub.num_caracteres > 0:
        return sub.num_caracteres
    return ESTIMACION_SIN_ESTADISTICAS


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
    extractor: Extractor = ejecutar_ffmpeg,
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
            _generar(db, trabajo, fabrica_traductor, extractor)
        except Exception as exc:  # noqa: BLE001 — todo fallo acaba en el trabajo
            db.rollback()
            trabajo.estado = EstadoTrabajo.FAILED
            trabajo.mensaje_error = str(exc) or type(exc).__name__
        else:
            trabajo.estado = EstadoTrabajo.DONE
            _marcar_traducido(db, trabajo)
        trabajo.fase = None
        trabajo.finalizado_en = _ahora()
        db.commit()


def _generar(
    db: Session,
    trabajo: TrabajoTraduccion,
    fabrica_traductor: FabricaTraductor,
    extractor: Extractor,
) -> None:
    sub_origen = db.get(ArchivoSubtitulo, trabajo.subtitulo_id) if trabajo.subtitulo_id else None
    sub_coreano = (
        db.get(ArchivoSubtitulo, trabajo.subtitulo_coreano_id)
        if trabajo.subtitulo_coreano_id
        else None
    )
    _extraer_si_hace_falta(db, trabajo, [s for s in (sub_origen, sub_coreano) if s], extractor)
    if sub_origen is not None and sub_origen.es_pista:
        _comprobar_pistas(db, trabajo, sub_origen, sub_coreano, fabrica_traductor)

    trabajo.fase = FaseTrabajo.GENERANDO
    db.commit()
    origen = _leer(trabajo.ruta_origen, sub_origen)
    trabajo.bloques_totales = len(origen)

    if trabajo.modo is ModoTrabajo.FUSION:
        resultado = alinear(origen, _leer(trabajo.ruta_coreano, sub_coreano))
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
        # La guía se vuelve a leer del disco: puede haberse editado mientras el trabajo
        # esperaba en cola. Se anota solo si el proveedor la aprovecha.
        guia = _guia_del_trabajo(sub_origen)
        if guia is not None and traductor.admite_guia:
            trabajo.guia = f"{guia.ruta} ({guia.huella})"
        # Cada bloque se envía como una frase (sus líneas unidas) y el coreano vuelve a
        # sus líneas al escribirlo: ver `subtitles/lineas.py`.
        enviados = [lineas.para_traducir(b.contenido) for b in origen]
        # El contexto se calcula aquí, sobre el capítulo entero: el proveedor solo ve
        # un lote de bloques y perdería los vecinos en los bordes de cada lote.
        contextos = (
            _contextos(enviados) if guia and guia.contexto and traductor.admite_guia else None
        )
        traducidos = _traducir_con_progreso(db, trabajo, traductor, enviados, guia, contextos)
        textos = [lineas.recolocar(b.contenido, t) for b, t in zip(origen, traducidos, strict=True)]

    bilingual.generar(origen, textos, Path(trabajo.ruta_bilingue))


def _extraer_si_hace_falta(
    db: Session, trabajo: TrabajoTraduccion, subs: list[ArchivoSubtitulo], extractor: Extractor
) -> None:
    """Saca del vídeo las pistas que use el trabajo y aún no estén en la caché.

    Origen y coreano del mismo MKV salen en la misma pasada; un coreano `.srt` no
    necesita nada.
    """
    videos = {s.video_id: s.video for s in subs if s.es_pista and not esta_extraida(s)}
    if not videos:
        return
    trabajo.fase = FaseTrabajo.EXTRAYENDO
    db.commit()
    for video in videos.values():
        extraccion.extraer(db, video, extractor)


def _comprobar_pistas(
    db: Session,
    trabajo: TrabajoTraduccion,
    origen: ArchivoSubtitulo,
    coreano: ArchivoSubtitulo | None,
    fabrica_traductor: FabricaTraductor,
) -> None:
    """Revisa lo que se eligió con los datos de la cabecera ahora que se conoce el
    texto de verdad. Mejor fallar aquí, con un motivo, que generar un bilingüe
    inservible o gastar cupo de más.
    """
    if origen.estado is EstadoSubtitulo.ERROR:
        raise ErrorTraduccion(origen.mensaje_error or f"{origen.nombre} no se puede leer")
    if origen.idioma_origen not in IDIOMAS_ORIGEN:
        raise ErrorTraduccion(
            f"Al extraerla, {origen.nombre} resulta no ser español ni inglés "
            f"({origen.idioma_origen.value}): elige otro origen"
        )
    if origen.num_bloques < MIN_BLOQUES:
        raise ErrorTraduccion(
            f"Al extraerla, {origen.nombre} solo tiene {origen.num_bloques} líneas de "
            "diálogo: es un forzado (carteles). Elige otro origen"
        )
    if trabajo.modo is ModoTrabajo.FUSION and coreano is not None:
        if coreano.estado is EstadoSubtitulo.ERROR or coreano.idioma_origen is not IDIOMA_DESTINO:
            raise ErrorTraduccion(
                f"Al extraerla, {coreano.nombre} no resulta ser coreano legible: "
                "se puede pedir con forzar_traduccion"
            )

    # La pista puede resultar inglesa aunque su etiqueta dijera español (o al revés):
    # el nombre del bilingüe lo dice (`ES-KO`/`EN-KO`).
    if origen.idioma_origen is not trabajo.idioma_origen:
        trabajo.idioma_origen = origen.idioma_origen
        destino = ruta_bilingue(
            obra_de(origen), Path(origen.carpeta.ruta), origen.idioma_origen, IDIOMA_DESTINO
        )
        trabajo.ruta_bilingue = str(destino)

    if trabajo.modo is ModoTrabajo.TRADUCCION:
        _ajustar_reserva(db, trabajo, origen.num_caracteres, fabrica_traductor)


def _ajustar_reserva(
    db: Session, trabajo: TrabajoTraduccion, exactos: int, fabrica_traductor: FabricaTraductor
) -> None:
    """Cambia lo reservado por la cifra exacta. Si es más de lo reservado (solo pasa
    con la estimación de las pistas sin estadísticas) y el proveedor ya no llega,
    falla antes de enviar nada: al reintentar, la elección buscará otro."""
    if exactos > trabajo.caracteres_previstos and trabajo.proveedor is not None:
        cupo = consumo.estado(db, trabajo.proveedor, fabrica_traductor, registry.limite_configurado)
        # `libre` ya descuenta lo que este trabajo tenía reservado: se le devuelve.
        if cupo.libre is not None and cupo.libre + trabajo.caracteres_previstos < exactos * MARGEN:
            raise ErrorTraduccion(
                f"Al extraer la pista son {exactos:,} caracteres y {trabajo.proveedor} ya no "
                f"tiene cupo suficiente: reinténtalo y se elegirá otro proveedor".replace(",", ".")
            )
    trabajo.caracteres_previstos = exactos
    db.commit()


def _leer(ruta: str, sub: ArchivoSubtitulo | None) -> list[Bloque]:
    """Los bloques del origen o del coreano de un trabajo.

    Con su fila, por el punto único de lectura (vale para `.srt` y pistas). Sin ella
    (un escaneo la borró mientras el trabajo esperaba), la ruta copiada al crear el
    trabajo, que solo sirve si es un fichero.
    """
    if sub is not None:
        return leer_bloques(sub)
    if not Path(ruta).is_file():
        raise ErrorTraduccion(f"{ruta} ya no está en la biblioteca: vuelve a escanear")
    return parsear(Path(ruta))


def _guia_del_trabajo(sub_origen: ArchivoSubtitulo | None) -> Guia | None:
    """La guía de la serie del origen, leída del disco. Sin su fila (un escaneo la
    borró) no se sabe su carpeta de biblioteca: se traduce sin guía."""
    if sub_origen is None:
        return None
    return guia_de(obra_de(sub_origen).directorio, Path(sub_origen.carpeta.ruta))


def _contextos(textos: list[str]) -> list[str]:
    """El contexto de cada bloque: los `VECINOS_DE_CONTEXTO` de antes y de después,
    en una línea. Así el proveedor ve la frase partida entre bloques y quién habla."""
    contextos = []
    for i in range(len(textos)):
        vecinos = textos[max(0, i - VECINOS_DE_CONTEXTO) : i]
        vecinos += textos[i + 1 : i + 1 + VECINOS_DE_CONTEXTO]
        contextos.append(" ".join(v.replace("\n", " ") for v in vecinos if v.strip()))
    return contextos


def _traducir_con_progreso(
    db: Session,
    trabajo: TrabajoTraduccion,
    traductor: Translator,
    textos: list[str],
    guia: Guia | None = None,
    contextos: list[str] | None = None,
) -> list[str]:
    traducidos: list[str] = []
    for inicio in range(0, len(textos), BLOQUES_POR_PASO):
        paso = textos[inicio : inicio + BLOQUES_POR_PASO]
        contextos_paso = contextos[inicio : inicio + BLOQUES_POR_PASO] if contextos else None
        resultado = traductor.traducir(
            paso, trabajo.idioma_origen, IDIOMA_DESTINO, guia, contextos_paso
        )
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

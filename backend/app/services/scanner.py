"""Escaneo de carpetas: descubre `.srt`, los parsea e inventaría en la base de datos.

El disco es la fuente de verdad. Cada escaneo **reconcilia** la base de datos con
lo que hay en disco: da de alta los subtítulos y los vídeos nuevos, reparsea los
subtítulos que cambiaron y borra los huérfanos. Lo ya traducido se redescubre por el
`.bilingue.srt`.

También se anota dónde hay una guía de traducción (`srt-bilingual.toml`), sin
leerla: es un índice para el árbol (ver `models/guide_file.py`).

Los vídeos se inventarían sin abrirlos, solo para que la biblioteca se pueda dibujar
aunque no haya ningún `.srt` al lado. Sus pistas incrustadas las sondea después, en
segundo plano, `services/mkv/sondeo.py` (Fase 5): aquí solo se respetan (no son
ficheros, así que no pueden quedar huérfanas por no aparecer en el recorrido) y se
les detecta el bilingüe igual que a un `.srt`.

Las carpetas ni se crean ni se borran aquí: de eso se encarga el CRUD de `/folders`.
El escaneo se limita a recorrer las que se le indiquen.
"""

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.enums import EXTENSIONES_VIDEO, EstadoSubtitulo, Idioma
from app.models.guide_file import ArchivoGuia
from app.models.library_folder import CarpetaBiblioteca
from app.models.media_file import ArchivoMedia
from app.models.subtitle_file import ArchivoSubtitulo
from app.schemas.scan import ResumenEscaneo
from app.services.mkv.extraccion import borrar_cache
from app.services.obras import Obra, agrupar_en_obras, directorio_de_obra, ruta_bilingue
from app.services.subtitles import srt_parser
from app.services.subtitles.naming import base_sin_idioma, es_fichero_bilingue

# Nombre exacto, con sus minúsculas: en el NAS (Linux) leerlo las distingue, y una
# guía indexada que luego no se pudiera leer engañaría al árbol.
from app.services.translation.guia import NOMBRE_FICHERO


# Versión de las reglas de análisis de subtítulos (idioma, flags…). Se sube cada vez
# que cambian, para que el siguiente escaneo reprocese también lo que no ha cambiado
# en disco. 1: detección por nombre (Fase 1). 2: separadores ampliados, flags y
# detección por contenido (Fase 3).
VERSION_ANALISIS = 2


def _ahora() -> datetime:
    return datetime.now(UTC)


def _idioma_destino() -> Idioma:
    """Idioma destino configurado, como `Idioma` (UNKNOWN si no se reconoce)."""
    try:
        return Idioma(settings.default_target_lang.upper())
    except ValueError:
        return Idioma.UNKNOWN


def escanear(db: Session, carpeta_ids: list[int] | None = None) -> ResumenEscaneo:
    """Reconcilia con el disco las carpetas pedidas y devuelve un resumen.

    Con `carpeta_ids` se escanean solo esas; sin él, todas las marcadas como activas.
    """
    resumen = ResumenEscaneo()

    consulta = select(CarpetaBiblioteca).order_by(CarpetaBiblioteca.ruta)
    if carpeta_ids is None:
        consulta = consulta.where(CarpetaBiblioteca.activa)
    else:
        consulta = consulta.where(CarpetaBiblioteca.id.in_(carpeta_ids))

    for carpeta in db.scalars(consulta).all():
        resumen.carpetas += 1
        _escanear_carpeta(db, carpeta, resumen)
        carpeta.ultimo_escaneo = _ahora()

    db.commit()
    return resumen


def _escanear_carpeta(db: Session, carpeta: CarpetaBiblioteca, resumen: ResumenEscaneo) -> None:
    base = Path(carpeta.ruta)
    # Solo los `.srt`: las pistas viven y mueren con su vídeo (cascada).
    subs_en_db = {sub.ruta: sub for sub in carpeta.subtitulos if not sub.es_pista}
    videos_en_db = {video.ruta: video for video in carpeta.videos}
    guias_en_db = {guia.ruta: guia for guia in carpeta.guias}
    subs_vistos: set[str] = set()
    videos_vistos: set[str] = set()
    guias_vistas: set[str] = set()

    if base.exists():
        # Un único recorrido para todo: la biblioteca puede estar en otro equipo y
        # cada pasada por la red cuesta.
        for ruta in base.rglob("*"):
            sufijo = ruta.suffix.lower()
            if ruta.name == NOMBRE_FICHERO:
                guias_vistas.add(str(ruta))
                if str(ruta) not in guias_en_db:
                    db.add(ArchivoGuia(carpeta=carpeta, ruta=str(ruta)))
                resumen.guias += 1
            elif sufijo == ".srt":
                if es_fichero_bilingue(ruta.name):
                    continue
                subs_vistos.add(str(ruta))
                _inventariar_subtitulo(db, carpeta, ruta, subs_en_db, resumen)
            elif sufijo in EXTENSIONES_VIDEO:
                videos_vistos.add(str(ruta))
                _inventariar_video(db, carpeta, ruta, videos_en_db, resumen)

    # Bilingües ya generados, por obra: van junto al vídeo y con su nombre, aunque el
    # origen viva en `Subs\` (ver `naming.ruta_bilingue_de_obra`), así que no se
    # pueden buscar junto a cada subtítulo. Solo cuentan los ficheros vistos en esta
    # pasada: los huérfanos aún siguen en las relaciones hasta el borrado de abajo.
    videos = [video for video in carpeta.videos if video.ruta in videos_vistos]
    subs = [
        sub
        for sub in carpeta.subtitulos
        if sub.ruta in subs_vistos or (sub.es_pista and sub.video.ruta in videos_vistos)
    ]
    for obra in agrupar_en_obras(videos, subs):
        for sub in obra.subtitulos:
            if sub.estado is not EstadoSubtitulo.ERROR:
                detectar_traducido(sub, obra)
                resumen.traducidos += sub.estado is EstadoSubtitulo.TRANSLATED

    # Huérfanos: filas cuyo fichero ya no está en disco.
    for clave, sub in subs_en_db.items():
        if clave not in subs_vistos:
            db.delete(sub)
            resumen.huerfanos_borrados += 1

    for clave, video in videos_en_db.items():
        if clave not in videos_vistos:
            borrar_cache(video.id)  # sus pistas extraídas
            db.delete(video)
            resumen.huerfanos_borrados += 1

    # Una guía borrada del disco deja de contar (no suma a los huérfanos, que hablan
    # de subtítulos y vídeos).
    for clave, guia in guias_en_db.items():
        if clave not in guias_vistas:
            db.delete(guia)


def _inventariar_subtitulo(
    db: Session,
    carpeta: CarpetaBiblioteca,
    ruta: Path,
    en_db: dict[str, ArchivoSubtitulo],
    resumen: ResumenEscaneo,
) -> None:
    stat = ruta.stat()
    sub = en_db.get(str(ruta))

    if sub is None:
        sub = ArchivoSubtitulo(carpeta=carpeta, ruta=str(ruta), nombre=ruta.name)
        db.add(sub)
        _procesar(sub, ruta, stat)
        resumen.nuevos += 1
    elif (
        sub.mtime != stat.st_mtime
        or sub.tamano_bytes != stat.st_size
        or sub.version_analisis != VERSION_ANALISIS
    ):
        _procesar(sub, ruta, stat)
        resumen.actualizados += 1
    else:
        resumen.sin_cambios += 1

    # El bilingüe se detecta después, por obra, en `_escanear_carpeta`: se comprueba
    # siempre (aunque el original no haya cambiado), porque puede aparecer o
    # desaparecer por su cuenta.
    resumen.total += 1
    if sub.estado == EstadoSubtitulo.ERROR:
        resumen.errores += 1


def _inventariar_video(
    db: Session,
    carpeta: CarpetaBiblioteca,
    ruta: Path,
    en_db: dict[str, ArchivoMedia],
    resumen: ResumenEscaneo,
) -> None:
    """Registra el contenedor sin abrirlo: solo su existencia y su huella en disco."""
    stat = ruta.stat()
    video = en_db.get(str(ruta))

    if video is None:
        db.add(
            ArchivoMedia(
                carpeta=carpeta,
                ruta=str(ruta),
                nombre=ruta.name,
                base=base_sin_idioma(ruta),
                mtime=stat.st_mtime,
                tamano_bytes=stat.st_size,
            )
        )
    elif video.mtime != stat.st_mtime or video.tamano_bytes != stat.st_size:
        video.mtime = stat.st_mtime
        video.tamano_bytes = stat.st_size
        video.base = base_sin_idioma(ruta)

    resumen.videos += 1


def _procesar(sub: ArchivoSubtitulo, ruta_srt: Path, stat) -> None:
    """Parsea el fichero y vuelca métricas/estado en la fila (o marca ERROR)."""
    sub.mtime = stat.st_mtime
    sub.tamano_bytes = stat.st_size
    sub.version_analisis = VERSION_ANALISIS
    try:
        bloques = srt_parser.parsear(ruta_srt)
    except Exception as exc:  # noqa: BLE001 — cualquier fallo de parseo → ERROR
        sub.estado = EstadoSubtitulo.ERROR
        sub.mensaje_error = str(exc)
        return

    info_nombre = srt_parser.analizar_nombre(ruta_srt.name)
    sub.num_caracteres = srt_parser.contar_caracteres(bloques)
    sub.num_bloques = srt_parser.contar_bloques(bloques)
    # Los bloques ya están en memoria: mirar el contenido no cuesta otra lectura.
    sub.idioma_origen = srt_parser.detectar_idioma(ruta_srt.name, bloques)
    sub.es_forzado = info_nombre.es_forzado
    sub.es_sdh = info_nombre.es_sdh
    sub.estado = EstadoSubtitulo.PENDING
    sub.mensaje_error = None


def detectar_traducidos_de_video(video: ArchivoMedia) -> None:
    """Detecta el bilingüe de las pistas de un vídeo recién sondeado.

    La obra de una pista es la de su vídeo (su carpeta y su nombre base), que es
    todo lo que hace falta para saber dónde estaría su bilingüe.
    """
    obra = Obra(directorio_de_obra(Path(video.ruta)), video.base)
    for pista in video.pistas:
        if pista.estado is not EstadoSubtitulo.ERROR:
            detectar_traducido(pista, obra)


def detectar_traducido(sub: ArchivoSubtitulo, obra: Obra) -> None:
    """Si existe en disco el bilingüe de la obra con este origen, marca TRANSLATED."""
    destino = _idioma_destino()
    if sub.idioma_origen is Idioma.UNKNOWN or destino is Idioma.UNKNOWN:
        sub.estado = EstadoSubtitulo.PENDING
        sub.ruta_bilingue = None
        sub.idioma_destino = None
        return

    bilingue = ruta_bilingue(obra, Path(sub.carpeta.ruta), sub.idioma_origen, destino)
    if bilingue.exists():
        sub.estado = EstadoSubtitulo.TRANSLATED
        sub.ruta_bilingue = str(bilingue)
        sub.idioma_destino = destino
    else:
        sub.estado = EstadoSubtitulo.PENDING
        sub.ruta_bilingue = None
        sub.idioma_destino = None

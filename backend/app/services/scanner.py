"""Escaneo de carpetas: descubre `.srt`, los parsea e inventaría en la base de datos.

El disco es la fuente de verdad. Cada escaneo **reconcilia** la base de datos con
lo que hay en disco: da de alta los subtítulos y los vídeos nuevos, reparsea los
subtítulos que cambiaron y borra los huérfanos. Lo ya traducido se redescubre por el
`.bilingue.srt`.

Los vídeos se inventarían sin abrirlos, solo para que la biblioteca se pueda dibujar
aunque no haya ningún `.srt` al lado (subtítulos embebidos → Fase 5).

Las carpetas ni se crean ni se borran aquí: de eso se encarga el CRUD de `/folders`.
El escaneo se limita a recorrer las que se le indiquen.
"""

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.enums import EXTENSIONES_VIDEO, EstadoSubtitulo, Idioma
from app.models.library_folder import CarpetaBiblioteca
from app.models.media_file import ArchivoMedia
from app.models.subtitle_file import ArchivoSubtitulo
from app.schemas.scan import ResumenEscaneo
from app.services.subtitles import srt_parser
from app.services.subtitles.naming import (
    base_sin_idioma,
    derivar_nombre_bilingue,
    es_fichero_bilingue,
)


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
    subs_en_db = {sub.ruta: sub for sub in carpeta.subtitulos}
    videos_en_db = {video.ruta: video for video in carpeta.videos}
    subs_vistos: set[str] = set()
    videos_vistos: set[str] = set()

    if base.exists():
        # Un único recorrido para las dos cosas: la biblioteca puede estar en otro
        # equipo y cada pasada por la red cuesta.
        for ruta in base.rglob("*"):
            sufijo = ruta.suffix.lower()
            if sufijo == ".srt":
                if es_fichero_bilingue(ruta.name):
                    continue
                subs_vistos.add(str(ruta))
                _inventariar_subtitulo(db, carpeta, ruta, subs_en_db, resumen)
            elif sufijo in EXTENSIONES_VIDEO:
                videos_vistos.add(str(ruta))
                _inventariar_video(db, carpeta, ruta, videos_en_db, resumen)

    # Huérfanos: filas cuyo fichero ya no está en disco.
    for clave, sub in subs_en_db.items():
        if clave not in subs_vistos:
            db.delete(sub)
            resumen.huerfanos_borrados += 1

    for clave, video in videos_en_db.items():
        if clave not in videos_vistos:
            db.delete(video)
            resumen.huerfanos_borrados += 1


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
    elif sub.mtime != stat.st_mtime or sub.tamano_bytes != stat.st_size:
        _procesar(sub, ruta, stat)
        resumen.actualizados += 1
    else:
        resumen.sin_cambios += 1

    # Detección de bilingüe siempre (coherencia con el disco aunque el original no
    # haya cambiado: el .bilingue.srt puede aparecer/desaparecer).
    if sub.estado != EstadoSubtitulo.ERROR:
        _detectar_traducido(sub, ruta)

    resumen.total += 1
    if sub.estado == EstadoSubtitulo.ERROR:
        resumen.errores += 1
    elif sub.estado == EstadoSubtitulo.TRANSLATED:
        resumen.traducidos += 1


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
    try:
        bloques = srt_parser.parsear(ruta_srt)
    except Exception as exc:  # noqa: BLE001 — cualquier fallo de parseo → ERROR
        sub.estado = EstadoSubtitulo.ERROR
        sub.mensaje_error = str(exc)
        return

    sub.num_caracteres = srt_parser.contar_caracteres(bloques)
    sub.num_bloques = srt_parser.contar_bloques(bloques)
    sub.idioma_origen = srt_parser.detectar_idioma_desde_nombre(ruta_srt.name)
    sub.estado = EstadoSubtitulo.PENDING
    sub.mensaje_error = None


def _detectar_traducido(sub: ArchivoSubtitulo, ruta_srt: Path) -> None:
    """Si existe en disco el bilingüe correspondiente, marca TRANSLATED."""
    destino = _idioma_destino()
    if sub.idioma_origen is Idioma.UNKNOWN or destino is Idioma.UNKNOWN:
        sub.estado = EstadoSubtitulo.PENDING
        sub.ruta_bilingue = None
        sub.idioma_destino = None
        return

    bilingue = derivar_nombre_bilingue(ruta_srt, sub.idioma_origen, destino)
    if bilingue.exists():
        sub.estado = EstadoSubtitulo.TRANSLATED
        sub.ruta_bilingue = str(bilingue)
        sub.idioma_destino = destino
    else:
        sub.estado = EstadoSubtitulo.PENDING
        sub.ruta_bilingue = None
        sub.idioma_destino = None

"""Escaneo de carpetas: descubre `.srt`, los parsea e inventaría en la base de datos.

El disco es la fuente de verdad. Cada escaneo **reconcilia** la base de datos con
lo que hay en disco: crea carpetas/subtítulos nuevos, reparsea los que cambiaron,
borra los huérfanos y elimina las carpetas que ya no están configuradas (la cascada
arrastra sus subtítulos). Lo ya traducido se redescubre por el `.bilingue.srt`.
"""

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.enums import EstadoSubtitulo, Idioma
from app.models.library_folder import CarpetaBiblioteca
from app.models.subtitle_file import ArchivoSubtitulo
from app.schemas.scan import ResumenEscaneo
from app.services.subtitles import srt_parser
from app.services.subtitles.naming import derivar_nombre_bilingue, es_fichero_bilingue


def _ahora() -> datetime:
    return datetime.now(UTC)


def _idioma_destino() -> Idioma:
    """Idioma destino configurado, como `Idioma` (UNKNOWN si no se reconoce)."""
    try:
        return Idioma(settings.default_target_lang.upper())
    except ValueError:
        return Idioma.UNKNOWN


def escanear(db: Session) -> ResumenEscaneo:
    """Reconcilia la base de datos con el disco y devuelve un resumen del escaneo."""
    resumen = ResumenEscaneo()
    configuradas = {str(Path(ruta).resolve()) for ruta in settings.carpetas}

    # 1. Borrar carpetas que ya no están configuradas (cascada → sus subtítulos).
    for carpeta in db.scalars(select(CarpetaBiblioteca)).all():
        if carpeta.ruta not in configuradas:
            db.delete(carpeta)
    db.flush()

    existentes = {c.ruta: c for c in db.scalars(select(CarpetaBiblioteca)).all()}

    # 2. Crear (si faltan) y escanear cada carpeta configurada.
    for ruta in sorted(configuradas):
        carpeta = existentes.get(ruta)
        if carpeta is None:
            carpeta = CarpetaBiblioteca(ruta=ruta)
            db.add(carpeta)
            db.flush()
        resumen.carpetas += 1
        _escanear_carpeta(db, carpeta, resumen)
        carpeta.ultimo_escaneo = _ahora()

    db.commit()
    return resumen


def _escanear_carpeta(db: Session, carpeta: CarpetaBiblioteca, resumen: ResumenEscaneo) -> None:
    base = Path(carpeta.ruta)
    en_db = {sub.ruta: sub for sub in carpeta.subtitulos}
    vistos: set[str] = set()

    if base.exists():
        for ruta_srt in base.rglob("*.srt"):
            if es_fichero_bilingue(ruta_srt.name):
                continue
            clave = str(ruta_srt)
            vistos.add(clave)
            stat = ruta_srt.stat()
            sub = en_db.get(clave)

            if sub is None:
                sub = ArchivoSubtitulo(carpeta=carpeta, ruta=clave, nombre=ruta_srt.name)
                db.add(sub)
                _procesar(sub, ruta_srt, stat)
                resumen.nuevos += 1
            elif sub.mtime != stat.st_mtime or sub.tamano_bytes != stat.st_size:
                _procesar(sub, ruta_srt, stat)
                resumen.actualizados += 1
            else:
                resumen.sin_cambios += 1

            # Detección de bilingüe siempre (coherencia con el disco aunque el
            # original no haya cambiado: el .bilingue.srt puede aparecer/desaparecer).
            if sub.estado != EstadoSubtitulo.ERROR:
                _detectar_traducido(sub, ruta_srt)

            resumen.total += 1
            if sub.estado == EstadoSubtitulo.ERROR:
                resumen.errores += 1
            elif sub.estado == EstadoSubtitulo.TRANSLATED:
                resumen.traducidos += 1

    # 3. Huérfanos: filas cuyo `.srt` ya no está en disco.
    for clave, sub in en_db.items():
        if clave not in vistos:
            db.delete(sub)
            resumen.huerfanos_borrados += 1


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

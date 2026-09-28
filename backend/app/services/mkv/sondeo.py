"""Sondeo de las pistas de subtítulo de los vídeos con `ffprobe`.

`ffprobe` solo lee la **cabecera** del contenedor: 0,3–0,8 s por fichero por la red,
frente a 1–1,5 min que cuesta extraer una pista (hay que leer el MKV entero, ver
`docs/plans/plan-fase5.md`). Por eso el sondeo va en el escaneo y la extracción no.

Aun así, la primera pasada por la biblioteca real son ~8 min, demasiado para una
petición HTTP: `POST /scan` inventaría como siempre y deja este sondeo en una tarea
de fondo (`sondear_pendientes`), que solo abre los vídeos nuevos o cambiados.

Cada pista ES/EN/KO (o sin idioma declarado) se guarda como una fila de
`subtitle_file` con `video_id`. Lo que dice la cabecera y cuánto fiarse:

- **Idioma**: la etiqueta ISO 639-2 (`spa`, `eng`, `kor`). Si falta, el título.
- **Forzado y SDH**: por el **título** (`Forced`, `FORZADOS`, `SDH`, `[CC]`…) y la
  marca `hearing_impaired`. La marca `forced` **se ignora**: en la biblioteca real la
  pista española de *Shingeki* la lleva y está completa.
- **Métricas**: las estadísticas que escribe mkvmerge, cuando las hay.
  `NUMBER_OF_FRAMES` es el número de líneas, exacto. `NUMBER_OF_BYTES` ronda el doble
  de los caracteres (cada línea ASS arrastra sus campos): solo vale como cota
  superior. Las cifras exactas llegan al extraer la pista.
"""

import json
import re
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.enums import (
    SUFIJOS_IDIOMA,
    TOKENS_FORZADO,
    TOKENS_SDH,
    EstadoSubtitulo,
    FormatoSubtitulo,
    Idioma,
)
from app.models.media_file import ArchivoMedia
from app.models.subtitle_file import ArchivoSubtitulo
from app.services.scanner import detectar_traducidos_de_video

type Sondeador = Callable[[Path], dict[str, Any]]
type FabricaSesion = Callable[[], Session]

# Códec de ffmpeg → formato. Lo que no esté aquí (subtítulos de teletexto, rarezas)
# se ignora: no hay forma de sacarle texto.
CODECS: dict[str, FormatoSubtitulo] = {
    "subrip": FormatoSubtitulo.SRT,
    "srt": FormatoSubtitulo.SRT,
    "ass": FormatoSubtitulo.ASS,
    "ssa": FormatoSubtitulo.ASS,
    "webvtt": FormatoSubtitulo.VTT,
    "mov_text": FormatoSubtitulo.MOV_TEXT,
    "hdmv_pgs_subtitle": FormatoSubtitulo.PGS,
    "dvd_subtitle": FormatoSubtitulo.VOBSUB,
}

# Solo se guardan las pistas que pueden llegar a ser origen o coreano. Un MKV de
# Netflix trae 33: guardar las 28 restantes solo llenaría de ruido el panel de
# candidatos. Las que no declaran idioma sí, porque el contenido puede decidirlo.
IDIOMAS_GUARDADOS: frozenset[Idioma] = frozenset({Idioma.ES, Idioma.EN, Idioma.KO, Idioma.UNKNOWN})
# Etiquetas de «idioma sin declarar» (ISO 639-2: indeterminado, sin contenido
# lingüístico, varios).
ETIQUETAS_SIN_IDIOMA: frozenset[str] = frozenset({"", "und", "zxx", "mul", "mis"})

# Palabras del título de una pista que la delatan como forzada. Más que en el nombre
# de un `.srt`: en el título, `Signs` o `Songs` son pistas de solo carteles o letras.
TOKENS_FORZADO_TITULO: frozenset[str] = TOKENS_FORZADO | {"signs", "sign", "songs", "carteles"}

_SEPARADORES = re.compile(r"[.\s_\-\[\]()/&,]+")


class ErrorSondeo(Exception):
    """`ffprobe` no pudo leer el vídeo."""


class FfprobeAusente(ErrorSondeo):
    """No se encuentra el ejecutable: no tiene sentido seguir con los demás vídeos."""


@dataclass(frozen=True, slots=True)
class PistaSondeada:
    """Una pista de subtítulo tal como la describe la cabecera del contenedor."""

    indice: int
    formato: FormatoSubtitulo
    idioma: Idioma
    # `True` si la etiqueta declara un idioma, pero uno que la app no conoce (`ara`,
    # `pol`…). Distinto de no declarar ninguno (`und`): ahí el contenido aún puede
    # decir que es español, y aquí no.
    idioma_ajeno: bool
    titulo: str | None
    es_forzado: bool
    es_sdh: bool
    num_bloques: int  # 0 si la cabecera no trae estadísticas
    num_bytes: int  # ídem; cota superior de los caracteres


def ejecutar_ffprobe(ruta: Path) -> dict[str, Any]:
    """Pide a `ffprobe` las pistas de subtítulo del vídeo, en JSON."""
    orden = [
        settings.ffprobe_path,
        "-v", "error",
        "-select_streams", "s",
        "-show_entries", "stream=index,codec_name:stream_tags:stream_disposition",
        "-of", "json",
        str(ruta),
    ]  # fmt: skip
    try:
        proceso = subprocess.run(
            orden, capture_output=True, text=True, encoding="utf-8", timeout=120, check=False
        )
    except FileNotFoundError as exc:
        raise FfprobeAusente(
            f"No se encuentra ffprobe ({settings.ffprobe_path}): instala ffmpeg o "
            "indica su ruta en FFPROBE_PATH"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ErrorSondeo("ffprobe no respondió en 2 minutos") from exc
    if proceso.returncode != 0:
        raise ErrorSondeo(proceso.stderr.strip() or f"ffprobe terminó con {proceso.returncode}")
    return json.loads(proceso.stdout or "{}")


def leer_pistas(salida: dict[str, Any]) -> list[PistaSondeada]:
    """Interpreta la salida JSON de `ffprobe`. Función pura: los tests le pasan
    salidas reales guardadas."""
    pistas: list[PistaSondeada] = []
    for stream in salida.get("streams", []):
        formato = CODECS.get(stream.get("codec_name", ""))
        if formato is None:
            continue
        etiquetas = {clave.upper(): valor for clave, valor in stream.get("tags", {}).items()}
        disposicion = stream.get("disposition", {})
        titulo = (etiquetas.get("TITLE") or "").strip() or None
        tokens = _tokens(titulo)
        etiqueta = (etiquetas.get("LANGUAGE") or "").lower()
        idioma = _idioma(etiqueta, tokens)

        pistas.append(
            PistaSondeada(
                indice=int(stream["index"]),
                formato=formato,
                idioma=idioma,
                idioma_ajeno=idioma is Idioma.UNKNOWN and etiqueta not in ETIQUETAS_SIN_IDIOMA,
                titulo=titulo,
                es_forzado=bool(tokens & TOKENS_FORZADO_TITULO),
                es_sdh=bool(tokens & TOKENS_SDH) or bool(disposicion.get("hearing_impaired")),
                num_bloques=_estadistica(etiquetas, "NUMBER_OF_FRAMES"),
                num_bytes=_estadistica(etiquetas, "NUMBER_OF_BYTES"),
            )
        )
    return pistas


def _tokens(titulo: str | None) -> set[str]:
    """Palabras del título, en minúscula. A diferencia del nombre de un `.srt`, aquí
    cuentan todas, no solo las del final: el título es texto libre (`English (Forced)`,
    `Latin American (Forced)`, `Forzados srt`)."""
    return {token.lower() for token in _SEPARADORES.split(titulo or "") if token}


def _idioma(etiqueta: str, tokens_titulo: set[str]) -> Idioma:
    """La etiqueta de idioma y, si no la hay (`und`), el título.

    Del título solo se aceptan palabras de tres letras o más (`spanish`, `eng`): las de
    dos (`it`, `de`, `hi`) aparecen como palabras corrientes en un título libre.
    """
    if (idioma := SUFIJOS_IDIOMA.get(etiqueta)) is not None:
        return idioma
    for token in tokens_titulo:
        if len(token) >= 3 and token in SUFIJOS_IDIOMA:
            return SUFIJOS_IDIOMA[token]
    return Idioma.UNKNOWN


def _estadistica(etiquetas: dict[str, str], nombre: str) -> int:
    """Una estadística de mkvmerge. A veces lleva el idioma pegado
    (`NUMBER_OF_FRAMES-eng`), así que se busca por prefijo. 0 si no está."""
    for clave, valor in etiquetas.items():
        if clave == nombre or clave.startswith(f"{nombre}-"):
            try:
                return int(valor)
            except ValueError:
                return 0
    return 0


def nombre_de_pista(pista: PistaSondeada) -> str:
    """Nombre que se enseña en la interfaz: `Pista 7 · NF_Spanish`."""
    return f"Pista {pista.indice}" + (f" · {pista.titulo}" if pista.titulo else "")


def reconciliar(video: ArchivoMedia, pistas: list[PistaSondeada]) -> None:
    """Actualiza las filas de pista del vídeo con lo sondeado.

    Las pistas se identifican por su índice en el contenedor: la misma pista conserva
    su fila (y con ella las referencias de sus trabajos). Las que ya no están se
    borran. Si el vídeo cambió, lo extraído de la versión anterior ya no vale.
    """
    existentes = {fila.indice_pista: fila for fila in video.pistas}
    vistas: set[int] = set()

    for pista in pistas:
        if pista.idioma not in IDIOMAS_GUARDADOS or pista.idioma_ajeno:
            continue
        vistas.add(pista.indice)
        fila = existentes.get(pista.indice)
        if fila is None:
            fila = ArchivoSubtitulo(
                carpeta=video.carpeta,
                ruta=f"{video.ruta}#{pista.indice}",
                indice_pista=pista.indice,
                estado=EstadoSubtitulo.PENDING,
            )
            video.pistas.append(fila)
        _volcar(fila, pista, video)

    for indice, fila in existentes.items():
        if indice not in vistas:
            video.pistas.remove(fila)  # `delete-orphan`: se borra la fila

    video.sondeado_mtime = video.mtime


def _volcar(fila: ArchivoSubtitulo, pista: PistaSondeada, video: ArchivoMedia) -> None:
    fila.nombre = nombre_de_pista(pista)
    fila.formato = pista.formato
    fila.idioma_origen = pista.idioma
    fila.titulo_pista = pista.titulo
    fila.es_forzado = pista.es_forzado
    fila.es_sdh = pista.es_sdh
    fila.num_bloques = pista.num_bloques
    fila.num_caracteres = pista.num_bytes
    fila.metricas_exactas = False
    fila.ruta_extraida = None
    # La huella en disco de una pista es la de su vídeo.
    fila.mtime = video.mtime
    fila.tamano_bytes = video.tamano_bytes
    if fila.estado is EstadoSubtitulo.ERROR:
        fila.estado = EstadoSubtitulo.PENDING
        fila.mensaje_error = None


# --- Tarea de fondo ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProgresoSondeo:
    """Cómo va el sondeo en curso (o el último), para la interfaz."""

    en_curso: bool = False
    hechos: int = 0
    total: int = 0
    errores: int = 0
    ultimo_error: str | None = None


# Estado del proceso: un solo usuario y un solo servidor, así que basta con memoria.
# El cerrojo evita dos sondeos a la vez si se escanea dos veces seguidas.
_progreso = ProgresoSondeo()
_cerrojo = threading.Lock()


def progreso() -> ProgresoSondeo:
    return _progreso


def sondear_pendientes(
    fabrica_sesion: FabricaSesion, sondeador: Sondeador = ejecutar_ffprobe
) -> None:
    """Sondea todos los vídeos nuevos o cambiados. Pensado para `BackgroundTasks`.

    Si ya hay un sondeo en marcha no arranca otro: el que corre vuelve a buscar
    pendientes antes de terminar, así que recoge también lo que el nuevo escaneo haya
    añadido. Un vídeo que falla se cuenta y se deja pendiente para el próximo
    escaneo; si falta `ffprobe`, se para todo.

    Commit por vídeo: por la red esto dura minutos, y la interfaz debe ir viendo
    las obras según se completan.
    """
    global _progreso
    if not _cerrojo.acquire(blocking=False):
        return
    try:
        _progreso = ProgresoSondeo(en_curso=True)
        fallidos: set[int] = set()
        with fabrica_sesion() as db:
            while pendientes := [i for i in _pendientes(db) if i not in fallidos]:
                _progreso = replace(_progreso, total=_progreso.hechos + len(pendientes))
                for video_id in pendientes:
                    try:
                        _sondear_uno(db, video_id, sondeador)
                    except FfprobeAusente as exc:
                        db.rollback()
                        _progreso = replace(
                            _progreso, errores=_progreso.errores + 1, ultimo_error=str(exc)
                        )
                        return
                    except Exception as exc:  # noqa: BLE001 — un vídeo roto no para el resto
                        db.rollback()
                        fallidos.add(video_id)
                        _progreso = replace(
                            _progreso, errores=_progreso.errores + 1, ultimo_error=str(exc)
                        )
                    _progreso = replace(_progreso, hechos=_progreso.hechos + 1)
    finally:
        _progreso = replace(_progreso, en_curso=False)
        _cerrojo.release()


def _pendientes(db: Session) -> list[int]:
    return list(
        db.scalars(
            select(ArchivoMedia.id)
            .where(
                or_(
                    ArchivoMedia.sondeado_mtime.is_(None),
                    ArchivoMedia.sondeado_mtime != ArchivoMedia.mtime,
                )
            )
            .order_by(ArchivoMedia.ruta)
        ).all()
    )


def _sondear_uno(db: Session, video_id: int, sondeador: Sondeador) -> None:
    video = db.get(ArchivoMedia, video_id)
    if video is None:  # lo borró un escaneo mientras tanto
        return
    reconciliar(video, leer_pistas(sondeador(Path(video.ruta))))
    # El bilingüe puede existir ya (generado antes, o a mano): mismo criterio que el
    # escaneo para los `.srt`.
    detectar_traducidos_de_video(video)
    db.commit()

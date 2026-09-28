"""Extracción de las pistas de subtítulo de un vídeo con `ffmpeg`, a una caché.

Extraer es lo caro de la Fase 5: en un MKV los subtítulos van intercalados con el
vídeo a lo largo de todo el fichero, así que hay que **leerlo entero**. Por la red,
1–1,5 min por episodio (~9 MB/s). Dos consecuencias:

- **Una sola pasada por vídeo**: se extraen a la vez todas sus pistas de texto
  guardadas (ES/EN/KO o sin idioma). Sacar tres cuesta lo mismo que sacar una, y así
  la fusión, que necesita dos, no lee el vídeo dos veces.
- **Caché**: `CACHE_DIR/pistas/<video_id>/<índice>.<ass|srt>`. Es reconstruible como
  la base de datos; si el vídeo cambia, el sondeo la invalida.

Las pistas ASS y SRT se copian tal cual (`-c:s copy`). Las WebVTT y las de texto de
MP4 se convierten a SRT, que es lo que leen los parsers.

Al terminar, cada pista se analiza como un `.srt` del escaneo: bloques y caracteres
**exactos** (ya sin carteles, en los ASS) y el idioma por el contenido, que manda si
es claro.
"""

import shutil
import subprocess
import threading
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models.enums import FORMATOS_IMAGEN, EstadoSubtitulo, FormatoSubtitulo, Idioma
from app.models.media_file import ArchivoMedia
from app.models.subtitle_file import ArchivoSubtitulo
from app.services.subtitles.lectura import esta_extraida, leer_fichero
from app.services.subtitles.srt_parser import (
    contar_bloques,
    contar_caracteres,
    detectar_idioma_desde_contenido,
)

# Formato de la pista → (extensión en la caché, códec de salida de ffmpeg).
SALIDAS: dict[FormatoSubtitulo, tuple[str, str]] = {
    FormatoSubtitulo.ASS: (".ass", "copy"),
    FormatoSubtitulo.SRT: (".srt", "copy"),
    FormatoSubtitulo.VTT: (".srt", "srt"),
    FormatoSubtitulo.MOV_TEXT: (".srt", "srt"),
}
# Leer un MKV de varios GB por la red puede ir para largo; más de una hora es que
# algo se ha colgado.
LIMITE_SEGUNDOS = 3600


class ErrorExtraccion(Exception):
    """`ffmpeg` no pudo extraer las pistas."""


@dataclass(frozen=True, slots=True)
class Salida:
    """Una pista a extraer: su índice en el contenedor, adónde y con qué códec."""

    indice: int
    destino: Path
    codec: str  # `copy` o `srt`


type Extractor = Callable[[Path, list[Salida]], None]


def ejecutar_ffmpeg(video: Path, salidas: list[Salida]) -> None:
    """Extrae varias pistas de una sola pasada por el vídeo."""
    orden = [settings.ffmpeg_path, "-v", "error", "-nostdin", "-y", "-i", str(video)]
    for salida in salidas:
        # El formato se indica a mano: el destino es un `.part` y ffmpeg no puede
        # deducirlo de la extensión.
        formato = "ass" if salida.destino.name.endswith(".ass.part") else "srt"
        orden += ["-map", f"0:{salida.indice}", "-c:s", salida.codec, "-f", formato]
        orden.append(str(salida.destino))
    try:
        proceso = subprocess.run(
            orden, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=LIMITE_SEGUNDOS, check=False,
        )  # fmt: skip
    except FileNotFoundError as exc:
        raise ErrorExtraccion(
            f"No se encuentra ffmpeg ({settings.ffmpeg_path}): instala ffmpeg o indica su "
            "ruta en FFMPEG_PATH"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ErrorExtraccion(f"ffmpeg no terminó en {LIMITE_SEGUNDOS // 60} min") from exc
    if proceso.returncode != 0:
        raise ErrorExtraccion(proceso.stderr.strip() or f"ffmpeg terminó con {proceso.returncode}")


def directorio_cache(video_id: int) -> Path:
    return Path(settings.cache_dir) / "pistas" / str(video_id)


def borrar_cache(video_id: int) -> None:
    """Olvida lo extraído de un vídeo (cambió en disco, o ya no existe)."""
    shutil.rmtree(directorio_cache(video_id), ignore_errors=True)


def extraibles(video: ArchivoMedia) -> list[ArchivoSubtitulo]:
    """Las pistas del vídeo que se pueden extraer y leer: las de texto."""
    return [p for p in video.pistas if p.formato not in FORMATOS_IMAGEN]


# Un cerrojo por vídeo: si un trabajo y el botón «Extraer pistas» coinciden, el
# segundo espera al primero y encuentra la caché hecha, en vez de leer el vídeo dos
# veces por la red.
_cerrojos: defaultdict[int, threading.Lock] = defaultdict(threading.Lock)


def extraer(
    db: Session, video: ArchivoMedia, extractor: Extractor = ejecutar_ffmpeg
) -> list[ArchivoSubtitulo]:
    """Extrae las pistas de texto del vídeo que aún no estén en la caché y las
    analiza. Devuelve las que ha extraído (vacía si ya estaba todo).

    Lanza `ErrorExtraccion` si ffmpeg falla; en ese caso no se toca ninguna fila.
    """
    with _cerrojos[video.id]:
        # Otro hilo puede haber extraído mientras se esperaba el cerrojo: se mira lo
        # que hay ahora en la base de datos, no lo que había en esta sesión.
        for pista in video.pistas:
            db.refresh(pista)
        pendientes = [p for p in extraibles(video) if not esta_extraida(p)]
        if not pendientes:
            return []

        directorio = directorio_cache(video.id)
        directorio.mkdir(parents=True, exist_ok=True)
        salidas: list[Salida] = []
        for pista in pendientes:
            extension, codec = SALIDAS[pista.formato]
            salidas.append(
                Salida(
                    pista.indice_pista, directorio / f"{pista.indice_pista}{extension}.part", codec
                )
            )

        try:
            extractor(Path(video.ruta), salidas)
        except BaseException:
            for salida in salidas:
                salida.destino.unlink(missing_ok=True)
            raise

        # Del `.part` al nombre definitivo solo cuando ffmpeg ha terminado bien: un
        # corte a medias no deja en la caché una pista truncada que parezca buena.
        for pista, salida in zip(pendientes, salidas, strict=True):
            definitivo = salida.destino.with_suffix("")
            salida.destino.replace(definitivo)
            _analizar(pista, definitivo)
        db.commit()
        return pendientes


def _analizar(pista: ArchivoSubtitulo, ruta: Path) -> None:
    """Vuelca en la fila las métricas exactas de la pista extraída."""
    pista.ruta_extraida = str(ruta)
    try:
        bloques = leer_fichero(ruta)
    except Exception as exc:  # noqa: BLE001 — cualquier fallo de parseo → ERROR
        pista.estado = EstadoSubtitulo.ERROR
        pista.mensaje_error = f"No se pudo leer la pista extraída: {exc}"
        return

    pista.num_bloques = contar_bloques(bloques)
    pista.num_caracteres = contar_caracteres(bloques)
    pista.metricas_exactas = True
    # Como con los `.srt`: si el contenido es claro, manda sobre la etiqueta (que
    # puede faltar, o mentir).
    por_contenido = detectar_idioma_desde_contenido(bloques)
    if por_contenido is not Idioma.UNKNOWN:
        pista.idioma_origen = por_contenido
    if pista.estado is EstadoSubtitulo.ERROR:
        pista.estado = EstadoSubtitulo.PENDING
        pista.mensaje_error = None


# --- En segundo plano (botón «Extraer pistas») ------------------------------------


@dataclass(frozen=True, slots=True)
class EstadoExtraccion:
    en_curso: bool
    error: str | None = None


# Por vídeo, lo que se ha pedido desde la interfaz. En memoria, como el progreso del
# sondeo: un solo usuario y un solo servidor.
_estados: dict[int, EstadoExtraccion] = {}


def estado(video_id: int) -> EstadoExtraccion | None:
    return _estados.get(video_id)


def marcar_pedida(video_id: int) -> None:
    """Se llama al encolar, para que la interfaz vea «extrayendo» desde ya."""
    _estados[video_id] = EstadoExtraccion(en_curso=True)


def extraer_en_segundo_plano(
    video_id: int,
    fabrica_sesion: Callable[[], Session],
    extractor: Extractor = ejecutar_ffmpeg,
) -> None:
    """Para `BackgroundTasks`: nunca deja escapar una excepción; el fallo queda en el
    estado del vídeo, que es donde la interfaz lo va a buscar."""
    _estados[video_id] = EstadoExtraccion(en_curso=True)
    try:
        with fabrica_sesion() as db:
            video = db.get(ArchivoMedia, video_id)
            if video is not None:
                extraer(db, video, extractor)
    except Exception as exc:  # noqa: BLE001
        _estados[video_id] = EstadoExtraccion(en_curso=False, error=str(exc) or type(exc).__name__)
    else:
        _estados[video_id] = EstadoExtraccion(en_curso=False)

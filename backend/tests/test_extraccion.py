"""Tests de la extracción de pistas a la caché (Fase 5, hito 2).

`ffmpeg` se sustituye por un extractor de pega que escribe en cada destino una pista
ASS inventada: lo que se prueba es qué se le pide, qué queda en la caché y cómo se
analiza, no el propio ffmpeg (eso se verifica contra la biblioteca real).
"""

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.videos import get_extractor
from app.main import app as fastapi_app
from app.models.enums import EstadoSubtitulo, Idioma
from app.models.library_folder import CarpetaBiblioteca
from app.models.media_file import ArchivoMedia
from app.models.subtitle_file import ArchivoSubtitulo
from app.services.mkv import extraccion
from app.services.mkv.extraccion import ErrorExtraccion, Salida, extraer
from app.services.mkv.sondeo import leer_pistas, reconciliar
from app.services.scanner import escanear
from app.services.subtitles.lectura import PistaSinExtraer, leer_bloques
from tests.conftest import escribir_video

Registrar = Callable[..., list[CarpetaBiblioteca]]
FIXTURES = Path(__file__).parent / "fixtures" / "ffprobe"

ESPANOL = "¿Qué es esto? No lo sé, pero está aquí y yo tengo que ir con ella."
COREANO = "이건 뭐야? 모르겠어, 하지만 여기 있어."
INGLES = "What is this? I don't know, but it's here and you have to go."


def ass(texto: str, lineas: int = 150, cartel: bool = True) -> str:
    """Una pista ASS de `lineas` diálogos (y un cartel, que el parser debe quitar)."""
    eventos = [
        f"Dialogue: 0,0:{i // 30:02d}:{i % 30 * 2:02d}.00,0:{i // 30:02d}:{i % 30 * 2:02d}.90,"
        f"Default,,0,0,0,,{texto}"
        for i in range(lineas)
    ]
    if cartel:
        eventos.append("Dialogue: 0,0:00:01.00,0:00:02.00,Sign,,0,0,0,,CARTEL")
    return (
        "[Script Info]\nScriptType: v4.00+\n\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        + "\n".join(eventos)
        + "\n"
    )


class FfmpegFalso:
    """Escribe en cada destino la pista que le toque según su índice, y apunta."""

    def __init__(self, pistas: dict[int, str]) -> None:
        self.pistas = pistas
        self.llamadas: list[tuple[Path, list[Salida]]] = []

    def __call__(self, video: Path, salidas: list[Salida]) -> None:
        self.llamadas.append((video, salidas))
        for salida in salidas:
            salida.destino.write_text(self.pistas.get(salida.indice, ass(INGLES)), encoding="utf-8")


def _ffprobe(nombre: str) -> dict:
    return json.loads((FIXTURES / f"{nombre}.json").read_text(encoding="utf-8"))


@pytest.fixture
def moonrise(db: Session, tmp_path: Path, registrar_carpetas: Registrar) -> ArchivoMedia:
    """Un vídeo con las pistas reales de *Moonrise* 01 ya sondeadas (sin extraer)."""
    registrar_carpetas(tmp_path)
    escribir_video(tmp_path / "Moonrise" / "Moonrise - 01.mkv")
    escanear(db)
    video = db.scalars(select(ArchivoMedia)).one()
    reconciliar(video, leer_pistas(_ffprobe("moonrise_01")))
    db.commit()
    return video


def _pista(video: ArchivoMedia, indice: int) -> ArchivoSubtitulo:
    return next(p for p in video.pistas if p.indice_pista == indice)


def test_una_sola_pasada_extrae_todas_las_pistas_de_texto(
    db: Session, moonrise: ArchivoMedia, cache_temporal: Path
) -> None:
    ffmpeg = FfmpegFalso({7: ass(ESPANOL), 25: ass(COREANO, 148)})

    extraidas = extraer(db, moonrise, ffmpeg)

    assert len(ffmpeg.llamadas) == 1
    video, salidas = ffmpeg.llamadas[0]
    assert video == Path(moonrise.ruta)
    assert sorted(s.indice for s in salidas) == [3, 4, 6, 7, 25]
    assert all(s.codec == "copy" for s in salidas)  # ASS tal cual
    assert len(extraidas) == 5

    espanol = _pista(moonrise, 7)
    assert espanol.metricas_exactas
    assert espanol.num_bloques == 150  # sin el cartel
    assert espanol.num_caracteres == 150 * len(ESPANOL)
    assert Path(espanol.ruta_extraida) == cache_temporal / "pistas" / str(moonrise.id) / "7.ass"
    assert _pista(moonrise, 25).num_bloques == 148
    # Nada a medias en la caché.
    assert not list((cache_temporal / "pistas").rglob("*.part"))


def test_lo_ya_extraido_no_se_vuelve_a_extraer(db: Session, moonrise: ArchivoMedia) -> None:
    ffmpeg = FfmpegFalso({})
    extraer(db, moonrise, ffmpeg)

    assert extraer(db, moonrise, ffmpeg) == []
    assert len(ffmpeg.llamadas) == 1


def test_si_la_cache_se_borra_se_extrae_otra_vez(db: Session, moonrise: ArchivoMedia) -> None:
    ffmpeg = FfmpegFalso({})
    extraer(db, moonrise, ffmpeg)
    extraccion.borrar_cache(moonrise.id)

    extraer(db, moonrise, ffmpeg)

    assert len(ffmpeg.llamadas) == 2


def test_si_ffmpeg_falla_no_queda_nada(
    db: Session, moonrise: ArchivoMedia, cache_temporal: Path
) -> None:
    def roto(_video: Path, salidas: list[Salida]) -> None:
        salidas[0].destino.write_text("a medias", encoding="utf-8")
        raise ErrorExtraccion("Invalid data found when processing input")

    with pytest.raises(ErrorExtraccion):
        extraer(db, moonrise, roto)

    assert not list(cache_temporal.rglob("*.*"))
    assert all(not p.metricas_exactas and p.ruta_extraida is None for p in moonrise.pistas)


def test_el_contenido_decide_el_idioma(db: Session, moonrise: ArchivoMedia) -> None:
    """Una pista etiquetada como inglés que en realidad es español (como el `spa.srt`
    inglés de la Fase 3, pero al revés)."""
    extraer(db, moonrise, FfmpegFalso({3: ass(ESPANOL)}))

    assert _pista(moonrise, 3).idioma_origen is Idioma.ES


def test_una_pista_ilegible_queda_en_error(db: Session, moonrise: ArchivoMedia) -> None:
    extraer(db, moonrise, FfmpegFalso({4: "esto no es un ASS"}))

    rota = _pista(moonrise, 4)
    assert rota.estado is EstadoSubtitulo.ERROR
    assert "No se pudo leer" in rota.mensaje_error
    assert _pista(moonrise, 7).estado is EstadoSubtitulo.PENDING


def test_las_pistas_webvtt_y_mp4_se_convierten_a_srt(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    registrar_carpetas(tmp_path)
    escribir_video(tmp_path / "Pelicula.mp4")
    escanear(db)
    video = db.scalars(select(ArchivoMedia)).one()
    salida = {
        "streams": [
            {"index": 2, "codec_name": "mov_text", "tags": {"language": "spa"}},
            {"index": 3, "codec_name": "hdmv_pgs_subtitle", "tags": {"language": "eng"}},
        ]
    }
    reconciliar(video, leer_pistas(salida))
    db.commit()
    ffmpeg = FfmpegFalso({})

    def como_srt(ruta: Path, salidas: list[Salida]) -> None:
        ffmpeg.llamadas.append((ruta, salidas))
        for s in salidas:
            s.destino.write_text("1\n00:00:01,000 --> 00:00:02,000\nHola\n", encoding="utf-8")

    extraer(db, video, como_srt)

    salidas = ffmpeg.llamadas[0][1]
    # La de imagen no se pide: no hay texto que sacar.
    assert [(s.indice, s.codec, s.destino.name) for s in salidas] == [(2, "srt", "2.srt.part")]


def test_leer_bloques_de_una_pista_sin_extraer_avisa(moonrise: ArchivoMedia) -> None:
    with pytest.raises(PistaSinExtraer):
        leer_bloques(_pista(moonrise, 7))


def test_un_video_que_cambia_pierde_su_cache(db: Session, moonrise: ArchivoMedia) -> None:
    extraer(db, moonrise, FfmpegFalso({}))
    ruta = Path(_pista(moonrise, 7).ruta_extraida)

    moonrise.mtime += 1  # lo que haría el escaneo al ver el vídeo cambiado
    reconciliar(moonrise, leer_pistas(_ffprobe("moonrise_01")))
    db.commit()

    assert not ruta.exists()
    assert _pista(moonrise, 7).ruta_extraida is None
    assert not _pista(moonrise, 7).metricas_exactas


def test_un_video_borrado_pierde_su_cache(db: Session, moonrise: ArchivoMedia) -> None:
    extraer(db, moonrise, FfmpegFalso({}))
    directorio = extraccion.directorio_cache(moonrise.id)
    assert directorio.exists()

    Path(moonrise.ruta).unlink()
    escanear(db)

    assert not directorio.exists()


# --- API ----------------------------------------------------------------------------


def test_candidatos_piden_extraer_y_despues_dan_muestra_y_calidad(
    client: TestClient, db: Session, moonrise: ArchivoMedia
) -> None:
    ffmpeg = FfmpegFalso({7: ass(ESPANOL), 25: ass(COREANO)})
    fastapi_app.dependency_overrides[get_extractor] = lambda: ffmpeg
    espanol = _pista(moonrise, 7)

    antes = client.get(f"/subtitles/{espanol.id}/candidatos").json()
    assert antes["extraccion_pendiente"] and antes["video_id"] == moonrise.id
    assert antes["muestra"] == [] and antes["calidad_alineacion"] is None

    respuesta = client.post(f"/videos/{moonrise.id}/extraer")
    assert respuesta.status_code == 202
    assert respuesta.json()["en_curso"]
    db.expire_all()  # la tarea de fondo escribió con otra sesión

    despues = client.get(f"/subtitles/{espanol.id}/candidatos").json()
    assert not despues["extraccion_pendiente"]
    assert not despues["extrayendo"] and despues["error_extraccion"] is None
    assert despues["muestra"][0]["origen"] == ESPANOL
    assert despues["muestra"][0]["coreano"] == COREANO
    assert despues["calidad_alineacion"] == 1.0  # mismos tiempos, como en Netflix

    # Ya está todo en la caché: pedirlo otra vez no lee el vídeo.
    assert client.post(f"/videos/{moonrise.id}/extraer").json()["en_curso"] is False
    assert len(ffmpeg.llamadas) == 1


def test_el_error_de_extraccion_llega_a_los_candidatos(
    client: TestClient, moonrise: ArchivoMedia
) -> None:
    def roto(_video: Path, _salidas: list[Salida]) -> None:
        raise ErrorExtraccion("No se encuentra ffmpeg")

    fastapi_app.dependency_overrides[get_extractor] = lambda: roto

    client.post(f"/videos/{moonrise.id}/extraer")

    candidatos = client.get(f"/subtitles/{_pista(moonrise, 7).id}/candidatos").json()
    assert candidatos["extraccion_pendiente"]
    assert candidatos["error_extraccion"] == "No se encuentra ffmpeg"


def test_extraer_un_video_sin_pistas_de_texto(
    client: TestClient, db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    registrar_carpetas(tmp_path)
    escribir_video(tmp_path / "Sin pistas.mkv")
    escanear(db)
    video = db.scalars(select(ArchivoMedia)).one()

    assert client.post(f"/videos/{video.id}/extraer").status_code == 409
    assert client.post("/videos/9999/extraer").status_code == 404

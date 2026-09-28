"""Tests de la generación de bilingües desde pistas incrustadas (Fase 5, hito 3).

Los tres casos que pidió el usuario: fusión de dos pistas del mismo MKV, fusión de
una pista con un `.srt` coreano externo, y traducción de una pista. Además, lo que
solo se sabe al extraer: la fase del trabajo, lo elegido que resulta no servir y el
ajuste de la reserva de cupo.

Las pistas son las reales de *Moonrise* 01 y *Shingeki* 01 (salidas de `ffprobe`
guardadas); ffmpeg y el proveedor son de pega.
"""

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api.dependencias import get_extractor, get_fabrica_traductor
from app.main import app as fastapi_app
from app.models.enums import EstadoSubtitulo, EstadoTrabajo, FaseTrabajo, Idioma, ModoTrabajo
from app.models.library_folder import CarpetaBiblioteca
from app.models.media_file import ArchivoMedia
from app.models.subtitle_file import ArchivoSubtitulo
from app.models.translation_job import TrabajoTraduccion
from app.services import trabajos
from app.services.mkv.extraccion import Salida
from app.services.mkv.sondeo import leer_pistas, reconciliar
from app.services.scanner import escanear
from app.services.translation.base import Consumo
from tests.conftest import TraductorFalso, cupo_de_sobra, escribir_srt, escribir_video
from tests.test_extraccion import COREANO, ESPANOL, INGLES, FfmpegFalso, ass

Registrar = Callable[..., list[CarpetaBiblioteca]]
FIXTURES = Path(__file__).parent / "fixtures" / "ffprobe"


def _ffprobe(nombre: str) -> dict:
    return json.loads((FIXTURES / f"{nombre}.json").read_text(encoding="utf-8"))


@pytest.fixture
def fabrica(db: Session) -> sessionmaker:
    return sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)


@pytest.fixture
def mkv(db: Session, tmp_path: Path, registrar_carpetas: Registrar) -> Callable[..., ArchivoMedia]:
    """Crea un vídeo con las pistas de una salida real de ffprobe, ya sondeado."""
    registrar_carpetas(tmp_path)

    def _crear(relativa: str, ffprobe: str) -> ArchivoMedia:
        ruta = escribir_video(tmp_path / relativa)
        escanear(db)
        video = db.scalars(select(ArchivoMedia).where(ArchivoMedia.ruta == str(ruta))).one()
        reconciliar(video, leer_pistas(_ffprobe(ffprobe)))
        db.commit()
        return video

    return _crear


def _pista(video: ArchivoMedia, indice: int) -> ArchivoSubtitulo:
    return next(p for p in video.pistas if p.indice_pista == indice)


def _ejecutar(
    db: Session,
    fabrica: sessionmaker,
    trabajo: TrabajoTraduccion,
    extractor,
    traductor: TraductorFalso | None = None,
) -> TrabajoTraduccion:
    traductor = traductor or TraductorFalso()
    trabajos.ejecutar(trabajo.id, fabrica, lambda _nombre: traductor, extractor)
    db.expire_all()
    return db.get(TrabajoTraduccion, trabajo.id)


def test_fusion_de_dos_pistas_del_mismo_mkv(
    db: Session, tmp_path: Path, fabrica: sessionmaker, mkv
) -> None:
    """*Moonrise*: español y coreano de Netflix, con los mismos tiempos. Sin cupo."""
    video = mkv("Moonrise/Moonrise - 01.mkv", "moonrise_01")
    ffmpeg = FfmpegFalso({7: ass(ESPANOL), 25: ass(COREANO)})

    [trabajo], _ = trabajos.crear(db, [_pista(video, 7).id], estados_cupo=cupo_de_sobra)
    assert (trabajo.modo, trabajo.caracteres_previstos) == (ModoTrabajo.FUSION, 0)
    trabajo = _ejecutar(db, fabrica, trabajo, ffmpeg)

    assert trabajo.estado is EstadoTrabajo.DONE, trabajo.mensaje_error
    assert trabajo.fase is None
    assert trabajo.calidad_alineacion == 1.0
    assert len(ffmpeg.llamadas) == 1  # las dos pistas en una sola pasada
    bilingue = tmp_path / "Moonrise" / "Moonrise - 01.ES-KO.bilingue.srt"
    assert Path(trabajo.ruta_bilingue) == bilingue
    assert f"{ESPANOL}\n{COREANO}" in bilingue.read_text(encoding="utf-8")
    assert _pista(video, 7).estado is EstadoSubtitulo.TRANSLATED


def test_fusion_de_una_pista_con_un_srt_coreano_externo(
    db: Session, tmp_path: Path, fabrica: sessionmaker, mkv
) -> None:
    """*Shingeki* no trae coreano; el `.srt` de al lado, sí."""
    ruta_kor = tmp_path / "Shingeki" / "Shingeki - 01.kor.srt"
    escribir_srt(ruta_kor, _srt(COREANO, 150))
    video = mkv("Shingeki/Shingeki - 01.mkv", "shingeki_01")
    espanol = next(p for p in video.pistas if p.idioma_origen is Idioma.ES)
    ffmpeg = FfmpegFalso({espanol.indice_pista: ass(ESPANOL)})

    [trabajo], _ = trabajos.crear(db, [espanol.id], estados_cupo=cupo_de_sobra)
    assert trabajo.ruta_coreano == str(ruta_kor)
    trabajo = _ejecutar(db, fabrica, trabajo, ffmpeg)

    assert trabajo.estado is EstadoTrabajo.DONE, trabajo.mensaje_error
    assert trabajo.calidad_alineacion == 1.0
    texto = (tmp_path / "Shingeki" / "Shingeki - 01.ES-KO.bilingue.srt").read_text(encoding="utf-8")
    assert f"{ESPANOL}\n{COREANO}" in texto


def test_traduccion_de_una_pista_sin_estadisticas(
    db: Session, tmp_path: Path, fabrica: sessionmaker, mkv
) -> None:
    video = mkv("Shingeki/Shingeki - 01.mkv", "shingeki_01")
    espanol = next(p for p in video.pistas if p.idioma_origen is Idioma.ES)
    traductor = TraductorFalso()

    [trabajo], _ = trabajos.crear(db, [espanol.id], estados_cupo=cupo_de_sobra)
    # Sin estadísticas en la cabecera: se reserva la estimación.
    assert trabajo.modo is ModoTrabajo.TRADUCCION
    assert trabajo.caracteres_previstos == trabajos.ESTIMACION_SIN_ESTADISTICAS
    trabajo = _ejecutar(
        db, fabrica, trabajo, FfmpegFalso({espanol.indice_pista: ass(ESPANOL)}), traductor
    )

    assert trabajo.estado is EstadoTrabajo.DONE, trabajo.mensaje_error
    exactos = 150 * len(ESPANOL)
    assert trabajo.caracteres_previstos == exactos  # corregida al extraer
    assert trabajo.num_caracteres == exactos
    assert sum(len(textos) for textos, *_ in traductor.llamadas) == 150  # sin el cartel
    texto = (tmp_path / "Shingeki" / "Shingeki - 01.ES-KO.bilingue.srt").read_text(encoding="utf-8")
    assert f"{ESPANOL}\n[KO] {ESPANOL}" in texto


def test_mientras_extrae_el_trabajo_esta_en_fase_extrayendo(
    db: Session, fabrica: sessionmaker, mkv
) -> None:
    video = mkv("Moonrise/Moonrise - 01.mkv", "moonrise_01")
    [trabajo], _ = trabajos.crear(db, [_pista(video, 7).id], estados_cupo=cupo_de_sobra)
    vistas: list[FaseTrabajo | None] = []
    ffmpeg = FfmpegFalso({7: ass(ESPANOL), 25: ass(COREANO)})

    def mirando(ruta: Path, salidas: list[Salida]) -> None:
        with fabrica() as otra:  # como el frontend, desde otra sesión
            vistas.append(otra.get(TrabajoTraduccion, trabajo.id).fase)
        ffmpeg(ruta, salidas)

    _ejecutar(db, fabrica, trabajo, mirando)

    assert vistas == [FaseTrabajo.EXTRAYENDO]


def test_con_las_pistas_ya_extraidas_no_se_vuelve_a_leer_el_video(
    db: Session, fabrica: sessionmaker, mkv
) -> None:
    video = mkv("Moonrise/Moonrise - 01.mkv", "moonrise_01")
    ffmpeg = FfmpegFalso({7: ass(ESPANOL), 25: ass(COREANO)})
    [primero], _ = trabajos.crear(db, [_pista(video, 7).id], estados_cupo=cupo_de_sobra)
    _ejecutar(db, fabrica, primero, ffmpeg)

    [segundo], _ = trabajos.crear(db, [_pista(video, 7).id], estados_cupo=cupo_de_sobra)
    segundo = _ejecutar(db, fabrica, segundo, ffmpeg)

    assert segundo.estado is EstadoTrabajo.DONE
    assert len(ffmpeg.llamadas) == 1


def test_si_al_extraerla_resulta_un_forzado_falla_sin_traducir(
    db: Session, fabrica: sessionmaker, mkv
) -> None:
    """La cabecera no decía nada, pero la pista solo trae 12 carteles."""
    video = mkv("Shingeki/Shingeki - 01.mkv", "shingeki_01")
    espanol = next(p for p in video.pistas if p.idioma_origen is Idioma.ES)
    traductor = TraductorFalso()
    [trabajo], _ = trabajos.crear(db, [espanol.id], estados_cupo=cupo_de_sobra)

    trabajo = _ejecutar(
        db, fabrica, trabajo, FfmpegFalso({espanol.indice_pista: ass(ESPANOL, 12)}), traductor
    )

    assert trabajo.estado is EstadoTrabajo.FAILED
    assert "12 líneas" in trabajo.mensaje_error and "forzado" in trabajo.mensaje_error
    assert traductor.llamadas == []
    assert trabajo.num_caracteres == 0


def test_si_al_extraerla_resulta_inglesa_el_bilingue_se_llama_en_ko(
    db: Session, tmp_path: Path, fabrica: sessionmaker, mkv
) -> None:
    video = mkv("Shingeki/Shingeki - 01.mkv", "shingeki_01")
    espanol = next(p for p in video.pistas if p.idioma_origen is Idioma.ES)
    [trabajo], _ = trabajos.crear(db, [espanol.id], estados_cupo=cupo_de_sobra)

    trabajo = _ejecutar(db, fabrica, trabajo, FfmpegFalso({espanol.indice_pista: ass(INGLES)}))

    assert trabajo.estado is EstadoTrabajo.DONE, trabajo.mensaje_error
    assert trabajo.idioma_origen is Idioma.EN
    assert trabajo.ruta_bilingue == str(tmp_path / "Shingeki" / "Shingeki - 01.EN-KO.bilingue.srt")
    assert Path(trabajo.ruta_bilingue).is_file()


def test_si_la_pista_real_no_cabe_en_el_cupo_falla_antes_de_enviar(
    db: Session, fabrica: sessionmaker, mkv
) -> None:
    """Reservados los 40.000 de la estimación, la pista extraída son 45.000 y al
    proveedor solo le quedaban esos 40.000."""
    video = mkv("Shingeki/Shingeki - 01.mkv", "shingeki_01")
    espanol = next(p for p in video.pistas if p.idioma_origen is Idioma.ES)
    [trabajo], _ = trabajos.crear(db, [espanol.id], estados_cupo=cupo_de_sobra)
    largo = (ESPANOL * 5)[:300]  # 150 líneas × 300 = 45.000 caracteres

    class CasiAgotado(TraductorFalso):
        def consumo(self) -> Consumo:
            return Consumo(usados=960_000, limite=1_000_000)

    traductor = CasiAgotado()
    trabajo = _ejecutar(
        db, fabrica, trabajo, FfmpegFalso({espanol.indice_pista: ass(largo)}), traductor
    )

    assert trabajo.estado is EstadoTrabajo.FAILED
    assert "45.000 caracteres" in trabajo.mensaje_error
    assert "reinténtalo" in trabajo.mensaje_error
    assert traductor.llamadas == []


def test_api_genera_desde_una_pista(client: TestClient, db: Session, tmp_path: Path, mkv) -> None:
    video = mkv("Moonrise/Moonrise - 01.mkv", "moonrise_01")
    fastapi_app.dependency_overrides[get_extractor] = lambda: FfmpegFalso(
        {7: ass(ESPANOL), 25: ass(COREANO)}
    )
    fastapi_app.dependency_overrides[get_fabrica_traductor] = lambda: lambda _n: TraductorFalso()

    respuesta = client.post("/translate", json={"subtitulo_ids": [_pista(video, 7).id]})

    assert respuesta.status_code == 202
    [creado] = respuesta.json()["trabajos"]
    trabajo = client.get(f"/translate/jobs/{creado['id']}").json()
    assert trabajo["estado"] == "DONE", trabajo["mensaje_error"]
    assert trabajo["modo"] == "FUSION"
    assert trabajo["fase"] is None
    assert (tmp_path / "Moonrise" / "Moonrise - 01.ES-KO.bilingue.srt").is_file()


def _srt(texto: str, bloques: int) -> str:
    """Un `.srt` con los mismos tiempos que `ass()`: 2 s por bloque, 0,9 s de duración."""
    salida = []
    for i in range(bloques):
        marca = f"00:{i // 30:02d}:{i % 30 * 2:02d}"
        salida.append(f"{i + 1}\n{marca},000 --> {marca},900\n{texto}\n")
    return "\n".join(salida)

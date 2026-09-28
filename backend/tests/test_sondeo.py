"""Tests del sondeo de pistas incrustadas (Fase 5, hito 1).

Las salidas de `ffprobe` de `tests/fixtures/ffprobe/` son **reales**, tomadas del
sondeo de la biblioteca del 2026-09-28: un MKV de Netflix con 33 pistas y
estadísticas (*Moonrise*), uno sin estadísticas y con la marca `forced` en una pista
completa (*Shingeki*), uno solo con pistas de imagen (*Better Call Saul*) y una
película con una pista `FORZADOS` sin marcar (*Agáchate, maldito*).
"""

import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api.scan import get_sondeador
from app.main import app as fastapi_app
from app.models.enums import EstadoSubtitulo, FormatoSubtitulo, Idioma
from app.models.library_folder import CarpetaBiblioteca
from app.models.media_file import ArchivoMedia
from app.models.subtitle_file import ArchivoSubtitulo
from app.services import trabajos
from app.services.mkv import sondeo
from app.services.mkv.sondeo import FfprobeAusente, leer_pistas, reconciliar, sondear_pendientes
from app.services.obras import obra_de
from app.services.scanner import escanear
from app.services.subtitles import renombrado
from app.services.subtitles.seleccion import MotivoDescarte, seleccionar
from tests.conftest import cupo_de_sobra, escribir_srt, escribir_video, srt_completo

Registrar = Callable[..., list[CarpetaBiblioteca]]
FIXTURES = Path(__file__).parent / "fixtures" / "ffprobe"


def _ffprobe(nombre: str) -> dict:
    return json.loads((FIXTURES / f"{nombre}.json").read_text(encoding="utf-8"))


def _pista(pistas: list[ArchivoSubtitulo], indice: int) -> ArchivoSubtitulo:
    return next(p for p in pistas if p.indice_pista == indice)


def _descarte(seleccion, sub: ArchivoSubtitulo) -> MotivoDescarte | None:
    return next(c.descarte for c in seleccion.candidatos if c.subtitulo is sub)


@pytest.fixture
def fabrica(db: Session) -> sessionmaker:
    """Sesiones contra la BD de pruebas, como las que abre la tarea de fondo."""
    return sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)


@pytest.fixture
def video(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> Callable[..., ArchivoMedia]:
    """Crea un vídeo de pega, lo escanea y devuelve su fila (aún sin sondear)."""
    registrar_carpetas(tmp_path)

    def _crear(relativa: str) -> ArchivoMedia:
        ruta = escribir_video(tmp_path / relativa)
        escanear(db)
        return db.scalars(select(ArchivoMedia).where(ArchivoMedia.ruta == str(ruta))).one()

    return _crear


# --- Lectura de la cabecera -------------------------------------------------------


def test_moonrise_lee_formato_idioma_titulo_y_estadisticas() -> None:
    pistas = {p.indice: p for p in leer_pistas(_ffprobe("moonrise_01"))}

    assert len(pistas) == 33
    assert all(p.formato is FormatoSubtitulo.ASS for p in pistas.values())
    espanol = pistas[7]
    assert (espanol.idioma, espanol.titulo) == (Idioma.ES, "NF_Spanish")
    # Líneas exactas y bytes como cota de los caracteres (lo medido: 292 y 15.099).
    assert (espanol.num_bloques, espanol.num_bytes) == (292, 15099)
    assert pistas[25].idioma is Idioma.KO


def test_shingeki_ignora_la_marca_forced_y_no_trae_estadisticas() -> None:
    """La pista española de *Shingeki* está marcada `forced` y es completa (287 líneas)."""
    espanol = next(p for p in leer_pistas(_ffprobe("shingeki_01")) if p.idioma is Idioma.ES)

    assert not espanol.es_forzado
    assert (espanol.num_bloques, espanol.num_bytes) == (0, 0)


def test_forzados_y_sdh_se_leen_del_titulo() -> None:
    salida = {
        "streams": [
            {"index": 2, "codec_name": "subrip", "tags": {"language": "spa", "title": "FORZADOS"}},
            {"index": 3, "codec_name": "subrip", "tags": {"language": "spa", "title": "Latin American (Forced)"}},
            {"index": 4, "codec_name": "ass", "tags": {"language": "eng", "title": "English[Signs]"}},
            {"index": 5, "codec_name": "subrip", "tags": {"language": "eng", "title": "English[CC]"}},
            {"index": 6, "codec_name": "subrip", "tags": {"language": "eng"},
             "disposition": {"hearing_impaired": 1}},
            {"index": 7, "codec_name": "subrip", "tags": {"language": "spa", "title": "Completos srt"}},
        ]
    }  # fmt: skip
    pistas = {p.indice: p for p in leer_pistas(salida)}

    assert [pistas[i].es_forzado for i in (2, 3, 4, 5, 6, 7)] == [
        True,
        True,
        True,
        False,
        False,
        False,
    ]
    assert [pistas[i].es_sdh for i in (5, 6, 7)] == [True, True, False]


def test_sin_etiqueta_de_idioma_se_mira_el_titulo() -> None:
    salida = {
        "streams": [
            {
                "index": 2,
                "codec_name": "subrip",
                "tags": {"language": "und", "title": "English Text"},
            },
            {"index": 3, "codec_name": "subrip", "tags": {"title": "Hi"}},  # dos letras: no
        ]
    }

    assert [p.idioma for p in leer_pistas(salida)] == [Idioma.EN, Idioma.UNKNOWN]


def test_estadisticas_con_el_idioma_pegado_y_codecs_desconocidos() -> None:
    salida = {
        "streams": [
            {"index": 2, "codec_name": "subrip", "tags": {"NUMBER_OF_FRAMES-eng": "812"}},
            {"index": 3, "codec_name": "dvb_teletext", "tags": {"language": "spa"}},
        ]
    }

    pistas = leer_pistas(salida)

    assert [(p.indice, p.num_bloques) for p in pistas] == [(2, 812)]


# --- Reconciliación con la base de datos ------------------------------------------


def test_reconciliar_guarda_solo_las_pistas_que_pueden_servir(db: Session, video) -> None:
    mkv = video("Moonrise/Moonrise - 01.mkv")

    reconciliar(mkv, leer_pistas(_ffprobe("moonrise_01")))
    db.commit()

    # De 33 pistas: las dos inglesas, las dos españolas y la coreana.
    assert sorted(p.indice_pista for p in mkv.pistas) == [3, 4, 6, 7, 25]
    espanol = _pista(mkv.pistas, 7)
    assert espanol.ruta == f"{mkv.ruta}#7"
    assert espanol.nombre == "Pista 7 · NF_Spanish"
    assert espanol.carpeta_id == mkv.carpeta_id
    assert not espanol.metricas_exactas
    assert espanol.es_pista
    assert mkv.sondeado_mtime == mkv.mtime


def test_resondear_conserva_las_filas_y_borra_las_que_ya_no_estan(db: Session, video) -> None:
    mkv = video("Moonrise/Moonrise - 01.mkv")
    reconciliar(mkv, leer_pistas(_ffprobe("moonrise_01")))
    db.commit()
    id_espanol = _pista(mkv.pistas, 7).id

    salida = _ffprobe("moonrise_01")
    salida["streams"] = [s for s in salida["streams"] if s["index"] != 25]  # sin coreano
    reconciliar(mkv, leer_pistas(salida))
    db.commit()

    assert sorted(p.indice_pista for p in mkv.pistas) == [3, 4, 6, 7]
    assert _pista(mkv.pistas, 7).id == id_espanol
    assert db.scalar(select(ArchivoSubtitulo).where(ArchivoSubtitulo.indice_pista == 25)) is None


# --- Selección con pistas ---------------------------------------------------------


def test_moonrise_castellano_de_origen_y_coreano_del_mismo_mkv(db: Session, video) -> None:
    mkv = video("Moonrise/Moonrise - 01.mkv")
    reconciliar(mkv, leer_pistas(_ffprobe("moonrise_01")))
    db.commit()

    seleccion = seleccionar(mkv.pistas)

    # `NF_Spanish(Latin_America)` tiene 297 líneas y `NF_Spanish` 292: gana el castellano.
    assert seleccion.origen is _pista(mkv.pistas, 7)
    assert seleccion.coreano is _pista(mkv.pistas, 25)


def test_shingeki_una_pista_sin_estadisticas_puede_ser_origen(db: Session, video) -> None:
    mkv = video("Shingeki/S1/Shingeki - 01.mkv")
    reconciliar(mkv, leer_pistas(_ffprobe("shingeki_01")))
    db.commit()

    seleccion = seleccionar(mkv.pistas)

    # 0 líneas no es «vacía» sino «no se sabe»: no la descarta por forzado encubierto.
    assert seleccion.origen is next(p for p in mkv.pistas if p.idioma_origen is Idioma.ES)
    assert seleccion.coreano is None


def test_jujutsu_las_lineas_de_cabecera_no_se_comparan_entre_pistas(db: Session, video) -> None:
    """La pista inglesa (fansub) declara 1023 «líneas» por los carteles y el karaoke;
    la española, completa, 390. Con la regla del 40 % el español quedaría descartado
    como forzado encubierto y el origen sería el inglés."""
    mkv = video("Jujutsu Kaisen/Jujutsu Kaisen - 01.mkv")
    reconciliar(mkv, leer_pistas(_ffprobe("jujutsu_kaisen_01")))
    db.commit()

    seleccion = seleccionar(mkv.pistas)

    assert (_pista(mkv.pistas, 2).num_bloques, _pista(mkv.pistas, 9).num_bloques) == (1023, 390)
    assert seleccion.origen is _pista(mkv.pistas, 9)  # castellano, no el latino (6)
    assert _descarte(seleccion, _pista(mkv.pistas, 6)) is None


def test_una_pista_con_menos_de_100_lineas_se_descarta_aunque_no_sean_exactas(
    db: Session, video
) -> None:
    mkv = video("Pelicula.mkv")
    salida = {
        "streams": [
            {"index": 2, "codec_name": "subrip", "tags": {"language": "spa", "NUMBER_OF_FRAMES": "33"}},
            {"index": 3, "codec_name": "subrip", "tags": {"language": "eng", "NUMBER_OF_FRAMES": "1400"}},
        ]
    }  # fmt: skip
    reconciliar(mkv, leer_pistas(salida))
    db.commit()

    seleccion = seleccionar(mkv.pistas)

    assert _descarte(seleccion, _pista(mkv.pistas, 2)) is MotivoDescarte.POCOS_BLOQUES
    assert seleccion.origen is _pista(mkv.pistas, 3)


def test_better_call_saul_las_pistas_de_imagen_no_sirven(db: Session, video) -> None:
    mkv = video("Better Call Saul/Day One.mkv")
    reconciliar(mkv, leer_pistas(_ffprobe("better_call_saul_day_one")))
    db.commit()

    seleccion = seleccionar(mkv.pistas)

    assert {p.formato for p in mkv.pistas} == {FormatoSubtitulo.PGS}
    assert not seleccion.elegible
    assert {_descarte(seleccion, p) for p in mkv.pistas} == {MotivoDescarte.IMAGEN}


def test_agachate_la_pista_forzados_no_es_origen(db: Session, video) -> None:
    mkv = video("Agachate maldito.mkv")
    reconciliar(mkv, leer_pistas(_ffprobe("agachate_maldito")))
    db.commit()

    seleccion = seleccionar(mkv.pistas)

    assert _descarte(seleccion, _pista(mkv.pistas, 3)) is MotivoDescarte.FORZADO
    assert seleccion.origen is _pista(mkv.pistas, 4)


def test_pista_de_origen_con_coreano_srt_externo(db: Session, tmp_path: Path, video) -> None:
    """El caso mixto que pidió el usuario: pista ES del MKV + `.srt` coreano al lado."""
    mkv = video("Shingeki/S1/Shingeki - 01.mkv")
    escribir_srt(
        tmp_path / "Shingeki/S1/Shingeki - 01.kor.srt", srt_completo(300, "안녕하세요 친구")
    )
    escanear(db)
    reconciliar(mkv, leer_pistas(_ffprobe("shingeki_01")))
    db.commit()

    obra = obra_de(mkv.pistas[0])
    seleccion = seleccionar(obra.subtitulos)

    assert seleccion.origen.es_pista and seleccion.origen.idioma_origen is Idioma.ES
    assert not seleccion.coreano.es_pista
    assert seleccion.coreano.nombre == "Shingeki - 01.kor.srt"


def test_un_srt_externo_gana_a_una_pista_del_mismo_idioma(
    db: Session, tmp_path: Path, video
) -> None:
    mkv = video("Agachate maldito.mkv")
    escribir_srt(tmp_path / "Agachate maldito.spa.srt", srt_completo(300))
    escanear(db)
    reconciliar(mkv, leer_pistas(_ffprobe("agachate_maldito")))
    db.commit()

    seleccion = seleccionar(obra_de(mkv.pistas[0]).subtitulos)

    assert not seleccion.origen.es_pista


# --- Tarea de fondo ---------------------------------------------------------------


def test_sondear_pendientes_solo_abre_lo_nuevo_o_cambiado(
    db: Session, fabrica: sessionmaker, video
) -> None:
    mkv = video("Moonrise/Moonrise - 01.mkv")
    abiertos: list[Path] = []

    def sondeador(ruta: Path) -> dict:
        abiertos.append(ruta)
        return _ffprobe("moonrise_01")

    sondear_pendientes(fabrica, sondeador)
    assert sondeo.progreso() == sondeo.ProgresoSondeo(en_curso=False, hechos=1, total=1)

    sondear_pendientes(fabrica, sondeador)  # nada pendiente: no abre nada
    assert abiertos == [Path(mkv.ruta)]

    # El vídeo cambia en disco: el siguiente escaneo lo marca y se vuelve a sondear.
    os.utime(mkv.ruta, (1_000_000_000, 1_000_000_000))
    escanear(db)
    sondear_pendientes(fabrica, sondeador)

    assert len(abiertos) == 2


def test_un_video_que_falla_se_cuenta_y_queda_pendiente(
    db: Session, fabrica: sessionmaker, video
) -> None:
    roto = video("Roto.mkv")
    bueno = video("Moonrise - 01.mkv")

    def sondeador(ruta: Path) -> dict:
        if ruta.name == "Roto.mkv":
            raise sondeo.ErrorSondeo("Invalid data found when processing input")
        return _ffprobe("moonrise_01")

    sondear_pendientes(fabrica, sondeador)

    progreso = sondeo.progreso()
    assert (progreso.hechos, progreso.errores) == (2, 1)
    assert "Invalid data" in progreso.ultimo_error
    db.expire_all()
    assert db.get(ArchivoMedia, roto.id).pendiente_de_sondeo
    assert not db.get(ArchivoMedia, bueno.id).pendiente_de_sondeo


def test_sin_ffprobe_se_para_todo(fabrica: sessionmaker, video) -> None:
    video("Uno.mkv")
    video("Dos.mkv")
    llamadas = 0

    def sondeador(_ruta: Path) -> dict:
        nonlocal llamadas
        llamadas += 1
        raise FfprobeAusente("No se encuentra ffprobe")

    sondear_pendientes(fabrica, sondeador)

    assert llamadas == 1
    assert sondeo.progreso().ultimo_error == "No se encuentra ffprobe"


# --- Integración con el escaneo ---------------------------------------------------


def test_el_escaneo_no_borra_las_pistas_y_si_se_van_con_su_video(
    db: Session, fabrica: sessionmaker, video
) -> None:
    mkv = video("Moonrise/Moonrise - 01.mkv")
    sondear_pendientes(fabrica, lambda _ruta: _ffprobe("moonrise_01"))

    resumen = escanear(db)

    assert resumen.huerfanos_borrados == 0
    assert db.scalar(select(ArchivoSubtitulo).where(ArchivoSubtitulo.video_id == mkv.id))

    Path(mkv.ruta).unlink()
    escanear(db)

    assert db.scalars(select(ArchivoSubtitulo)).all() == []


def test_un_bilingue_ya_generado_marca_las_pistas_traducidas(
    db: Session, tmp_path: Path, fabrica: sessionmaker, video
) -> None:
    video("Moonrise/Moonrise - 01.mkv")
    escribir_srt(tmp_path / "Moonrise/Moonrise - 01.ES-KO.bilingue.srt")

    sondear_pendientes(fabrica, lambda _ruta: _ffprobe("moonrise_01"))

    espanol = db.scalar(select(ArchivoSubtitulo).where(ArchivoSubtitulo.indice_pista == 7))
    assert espanol.estado is EstadoSubtitulo.TRANSLATED
    assert espanol.ruta_bilingue.endswith("Moonrise - 01.ES-KO.bilingue.srt")


def test_las_pistas_no_se_renombran_y_si_se_pueden_generar(
    db: Session, fabrica: sessionmaker, video
) -> None:
    video("Moonrise/Moonrise - 01.mkv")
    sondear_pendientes(fabrica, lambda _ruta: _ffprobe("moonrise_01"))
    db.expire_all()  # el sondeo escribió con otra sesión
    espanol = db.scalar(select(ArchivoSubtitulo).where(ArchivoSubtitulo.indice_pista == 7))

    assert renombrado.proponer(db) == []
    creados, rechazos = trabajos.crear(db, [espanol.id], estados_cupo=cupo_de_sobra)
    assert rechazos == []
    assert creados[0].ruta_origen.endswith("Moonrise - 01.mkv#7")
    assert creados[0].ruta_coreano.endswith("Moonrise - 01.mkv#25")


def test_api_escanear_sondea_en_segundo_plano_y_el_arbol_ve_las_pistas(
    client: TestClient, db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    escribir_video(tmp_path / "Moonrise" / "Moonrise - 01.mkv")
    registrar_carpetas(tmp_path)
    fastapi_app.dependency_overrides[get_sondeador] = lambda: lambda _ruta: _ffprobe("moonrise_01")

    assert client.post("/scan").status_code == 200
    # La tarea de fondo escribe con su propia sesión; la del test (compartida por todas
    # las peticiones, a diferencia de producción) tiene las colecciones en caché.
    db.expire_all()

    assert client.get("/scan/sondeo").json() == {
        "en_curso": False, "hechos": 1, "total": 1, "errores": 0, "ultimo_error": None,
    }  # fmt: skip
    obra = client.get("/library/tree").json()[0]["hijos"][0]["hijos"][0]
    assert obra["estado_obra"] == "PENDIENTE"
    assert obra["idioma_origen"] == "ES"
    assert obra["subtitulo_coreano_id"] is not None

    candidatos = client.get(f"/subtitles/{obra['subtitulo_origen_id']}/candidatos").json()
    # Sin extraer no hay muestra ni calidad de fusión (costaría leer el MKV entero).
    assert candidatos["muestra"] == []
    assert candidatos["calidad_alineacion"] is None
    origen = next(
        c for c in candidatos["candidatos"] if c["subtitulo_id"] == candidatos["origen_id"]
    )
    assert origen["es_pista"] and origen["indice_pista"] == 7
    assert origen["titulo_pista"] == "NF_Spanish"
    assert origen["formato"] == "ASS"
    assert not origen["metricas_exactas"]

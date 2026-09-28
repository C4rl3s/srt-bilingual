"""Tests de la API de generación de bilingües y del renombrado.

`TestClient` ejecuta las `BackgroundTasks` al terminar cada petición, así que tras un
`POST /translate` el trabajo ya ha corrido de verdad, con el traductor falso y una
sesión contra la BD de pruebas.
"""

import random
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.translate import get_fabrica_sesion, get_fabrica_traductor
from app.main import app as fastapi_app
from app.models.enums import EstadoSubtitulo, Idioma
from app.models.library_folder import CarpetaBiblioteca
from app.models.subtitle_file import ArchivoSubtitulo
from app.services import trabajos
from app.services.scanner import escanear
from app.services.translation.base import CuotaAgotada
from tests.conftest import TraductorFalso, escribir_srt, escribir_video, srt_completo

Registrar = Callable[..., list[CarpetaBiblioteca]]


class TraductorQueSeAgota(TraductorFalso):
    """Traduce el primer paso y en el segundo se queda sin cuota."""

    def traducir(self, textos: list[str], origen: Idioma, destino: Idioma) -> list[str]:
        if self.llamadas:
            raise CuotaAgotada("Cuota de pega agotada")
        return super().traducir(textos, origen, destino)


@pytest.fixture
def traductor() -> TraductorFalso:
    return TraductorFalso()


@pytest.fixture
def api(client: TestClient, engine: Engine, traductor: TraductorFalso) -> Iterator[TestClient]:
    """Cliente cuya tarea de fondo usa la BD de pruebas y el traductor falso."""
    fabrica = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    fastapi_app.dependency_overrides[get_fabrica_sesion] = lambda: fabrica
    fastapi_app.dependency_overrides[get_fabrica_traductor] = lambda: lambda _nombre: traductor
    yield client


def _srt(tramos: list[tuple[float, float, str]]) -> str:
    def marca(segundos: float) -> str:
        ms = round(segundos * 1000)
        return (
            f"{ms // 3_600_000:02d}:{ms // 60_000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
        )

    return "\n".join(
        f"{i + 1}\n{marca(ini)} --> {marca(fin)}\n{texto}\n"
        for i, (ini, fin, texto) in enumerate(tramos)
    )


def _sub(db: Session, nombre: str) -> ArchivoSubtitulo:
    db.expire_all()  # la tarea de fondo escribió con otra sesión
    return db.scalars(select(ArchivoSubtitulo).where(ArchivoSubtitulo.nombre == nombre)).one()


def _pelicula(raiz: Path, registrar: Registrar, db: Session, **subtitulos: str) -> Path:
    """Carpeta con `Pelicula.mkv` y los subtítulos dados (`es=contenido`, …)."""
    escribir_video(raiz / "Pelicula.mkv")
    for sufijo, contenido in subtitulos.items():
        escribir_srt(raiz / f"Pelicula.{sufijo}.srt", contenido)
    registrar(raiz)
    escanear(db)
    return raiz


def test_traduce_y_escribe_el_bilingue(
    api: TestClient,
    db: Session,
    tmp_path: Path,
    registrar_carpetas: Registrar,
    traductor: TraductorFalso,
) -> None:
    _pelicula(tmp_path, registrar_carpetas, db, es=srt_completo())
    origen = _sub(db, "Pelicula.es.srt")

    respuesta = api.post("/translate", json={"subtitulo_ids": [origen.id]})

    assert respuesta.status_code == 202
    (trabajo,) = respuesta.json()["trabajos"]
    assert trabajo["modo"] == "TRADUCCION"
    final = api.get(f"/translate/jobs/{trabajo['id']}").json()
    assert final["estado"] == "DONE", final["mensaje_error"]
    assert final["proveedor"] == "falso"
    assert final["num_caracteres"] == 120 * len("Hola, mundo.")
    assert final["bloques_procesados"] == final["bloques_totales"] == 120
    # 120 bloques en pasos de 50: tres llamadas al proveedor.
    assert [len(textos) for textos, _, _ in traductor.llamadas] == [50, 50, 20]

    bilingue = tmp_path / "Pelicula.ES-KO.bilingue.srt"
    assert final["ruta_bilingue"] == str(bilingue)
    assert "Hola, mundo.\n[KO] Hola, mundo." in bilingue.read_text(encoding="utf-8")
    assert _sub(db, "Pelicula.es.srt").estado is EstadoSubtitulo.TRANSLATED


def test_con_coreano_fusiona_sin_gastar_cuota(
    api: TestClient,
    db: Session,
    tmp_path: Path,
    registrar_carpetas: Registrar,
    traductor: TraductorFalso,
) -> None:
    _pelicula(tmp_path, registrar_carpetas, db, es=srt_completo(), ko=srt_completo(texto="안녕."))
    origen = _sub(db, "Pelicula.es.srt")

    (trabajo,) = api.post("/translate", json={"subtitulo_ids": [origen.id]}).json()["trabajos"]

    final = api.get(f"/translate/jobs/{trabajo['id']}").json()
    assert (final["modo"], final["estado"]) == ("FUSION", "DONE")
    assert final["num_caracteres"] == 0 and final["proveedor"] is None
    assert final["calidad_alineacion"] == 1.0
    assert traductor.llamadas == []
    assert "Hola, mundo.\n안녕." in (tmp_path / "Pelicula.ES-KO.bilingue.srt").read_text(
        encoding="utf-8"
    )


def test_una_fusion_mala_falla_y_no_traduce_por_su_cuenta(
    api: TestClient,
    db: Session,
    tmp_path: Path,
    registrar_carpetas: Registrar,
    traductor: TraductorFalso,
) -> None:
    """Gastar cuota lo decide el usuario: sin `forzar_traduccion` no se traduce."""
    azar = random.Random(3)
    ajeno, t = [], 5.0
    for _ in range(120):  # un coreano de otra película: ritmo sin relación
        duracion = azar.uniform(1.0, 4.0)
        ajeno.append((t, t + duracion, "다른 영화"))
        t += duracion + azar.uniform(0.5, 9.0)
    _pelicula(tmp_path, registrar_carpetas, db, es=srt_completo(), ko=_srt(ajeno))
    origen = _sub(db, "Pelicula.es.srt")

    (trabajo,) = api.post("/translate", json={"subtitulo_ids": [origen.id]}).json()["trabajos"]

    final = api.get(f"/translate/jobs/{trabajo['id']}").json()
    assert (final["modo"], final["estado"]) == ("FUSION", "FAILED")
    assert "forzar_traduccion" in final["mensaje_error"]
    assert traductor.llamadas == []
    assert not (tmp_path / "Pelicula.ES-KO.bilingue.srt").exists()

    # Con forzar_traduccion, sí.
    (forzado,) = api.post(
        "/translate", json={"subtitulo_ids": [origen.id], "forzar_traduccion": True}
    ).json()["trabajos"]
    final = api.get(f"/translate/jobs/{forzado['id']}").json()
    assert (final["modo"], final["estado"]) == ("TRADUCCION", "DONE")


def test_si_se_agota_la_cuota_el_trabajo_falla_y_cuenta_lo_enviado(
    api: TestClient, db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    fastapi_app.dependency_overrides[get_fabrica_traductor] = lambda: (
        lambda _nombre: TraductorQueSeAgota()
    )
    _pelicula(tmp_path, registrar_carpetas, db, es=srt_completo())
    origen = _sub(db, "Pelicula.es.srt")

    (trabajo,) = api.post("/translate", json={"subtitulo_ids": [origen.id]}).json()["trabajos"]

    final = api.get(f"/translate/jobs/{trabajo['id']}").json()
    assert final["estado"] == "FAILED"
    assert "Cuota de pega agotada" in final["mensaje_error"]
    # El primer paso ya lo cobró el proveedor: cuenta para la cuota de la Fase 4.
    assert final["num_caracteres"] == 50 * len("Hola, mundo.")
    assert not (tmp_path / "Pelicula.ES-KO.bilingue.srt").exists()
    assert _sub(db, "Pelicula.es.srt").estado is EstadoSubtitulo.PENDING


def test_rechaza_lo_que_no_sirve_de_origen_sin_fallar_entera(
    api: TestClient, db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    _pelicula(tmp_path, registrar_carpetas, db, es=srt_completo(), ko=srt_completo(texto="안녕."))
    espanol, coreano = _sub(db, "Pelicula.es.srt"), _sub(db, "Pelicula.ko.srt")

    respuesta = api.post("/translate", json={"subtitulo_ids": [espanol.id, coreano.id, 9999]})

    assert respuesta.status_code == 202
    cuerpo = respuesta.json()
    assert len(cuerpo["trabajos"]) == 1
    assert {r["subtitulo_id"] for r in cuerpo["rechazados"]} == {coreano.id, 9999}


def test_no_duplica_un_trabajo_activo(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    _pelicula(tmp_path, registrar_carpetas, db, es=srt_completo())
    origen = _sub(db, "Pelicula.es.srt")

    (primero,), _ = trabajos.crear(db, [origen.id])
    (segundo,), _ = trabajos.crear(db, [origen.id])  # aún en QUEUED: no se ha ejecutado

    assert segundo.id == primero.id


def test_un_origen_en_subs_escribe_el_bilingue_junto_al_video(
    api: TestClient, db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    """Y el siguiente escaneo lo reconoce: la detección es por obra, no por fichero."""
    pelicula = tmp_path / "Jaws (1975)"
    escribir_video(pelicula / "Jaws.1975.mp4")
    escribir_srt(pelicula / "Subs" / "Spanish.spa.srt", srt_completo())
    registrar_carpetas(tmp_path)
    escanear(db)
    origen = _sub(db, "Spanish.spa.srt")

    (trabajo,) = api.post("/translate", json={"subtitulo_ids": [origen.id]}).json()["trabajos"]

    bilingue = pelicula / "Jaws.1975.ES-KO.bilingue.srt"
    assert api.get(f"/translate/jobs/{trabajo['id']}").json()["ruta_bilingue"] == str(bilingue)
    assert bilingue.exists()
    resumen = escanear(db)
    assert resumen.traducidos == 1
    arbol = api.get("/library/tree").json()
    assert arbol[0]["num_dual"] == 1


def test_listar_trabajos_activos(
    api: TestClient, db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    _pelicula(tmp_path, registrar_carpetas, db, es=srt_completo())
    origen = _sub(db, "Pelicula.es.srt")
    api.post("/translate", json={"subtitulo_ids": [origen.id]})

    assert len(api.get("/translate/jobs").json()) == 1
    assert api.get("/translate/jobs", params={"activos": True}).json() == []
    assert api.get("/translate/jobs/9999").status_code == 404


def test_candidatos_de_una_obra(
    api: TestClient, db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    _pelicula(
        tmp_path,
        registrar_carpetas,
        db,
        es=srt_completo(),
        ko=srt_completo(texto="안녕."),
        fre=srt_completo(texto="Bonjour."),
    )
    espanol, coreano = _sub(db, "Pelicula.es.srt"), _sub(db, "Pelicula.ko.srt")

    cuerpo = api.get(f"/subtitles/{coreano.id}/candidatos").json()  # desde cualquier hermano

    assert cuerpo["obra"] == "Pelicula"
    assert (cuerpo["origen_id"], cuerpo["coreano_id"]) == (espanol.id, coreano.id)
    assert cuerpo["calidad_alineacion"] == 1.0 and cuerpo["fusion_aceptable"] is True
    descartes = {c["nombre"]: c["descarte"] for c in cuerpo["candidatos"]}
    assert descartes == {
        "Pelicula.es.srt": None,
        "Pelicula.ko.srt": None,
        "Pelicula.fre.srt": "IDIOMA",
    }
    assert api.get("/subtitles/9999/candidatos").status_code == 404


def test_renombrado_por_la_api(
    api: TestClient, db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    escribir_video(tmp_path / "Psycho.1960.mp4")
    escribir_srt(
        tmp_path / "Psycho.srt", srt_completo(texto="What are you doing here? I don't know.")
    )
    registrar_carpetas(tmp_path)
    escanear(db)

    (propuesta,) = api.get("/renombrado/propuestas").json()
    assert Path(propuesta["ruta_nueva"]).name == "Psycho.1960.eng.srt"

    resultado = api.post("/renombrado", json={"subtitulo_ids": [propuesta["subtitulo_id"]]}).json()

    assert len(resultado["renombrados"]) == 1 and resultado["rechazados"] == []
    assert (tmp_path / "Psycho.1960.eng.srt").exists()

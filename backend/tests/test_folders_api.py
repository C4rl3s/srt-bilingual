"""Tests del CRUD de carpetas vigiladas (`/folders`)."""

from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.library_folder import CarpetaBiblioteca
from app.models.subtitle_file import ArchivoSubtitulo
from tests.conftest import escribir_srt

Registrar = Callable[..., list[CarpetaBiblioteca]]


def test_listar_sin_carpetas_devuelve_lista_vacia(client: TestClient) -> None:
    respuesta = client.get("/folders")

    assert respuesta.status_code == 200
    assert respuesta.json() == []


def test_alta_de_carpeta(client: TestClient, tmp_path: Path) -> None:
    respuesta = client.post("/folders", json={"ruta": str(tmp_path)})

    assert respuesta.status_code == 201
    datos = respuesta.json()
    assert datos["ruta"] == str(tmp_path.resolve())
    assert datos["activa"] is True
    assert datos["ultimo_escaneo"] is None
    assert datos["num_subtitulos"] == 0


def test_alta_de_ruta_inexistente_devuelve_400(client: TestClient, tmp_path: Path) -> None:
    respuesta = client.post("/folders", json={"ruta": str(tmp_path / "no-existe")})

    assert respuesta.status_code == 400


def test_alta_de_un_fichero_devuelve_400(client: TestClient, tmp_path: Path) -> None:
    fichero = escribir_srt(tmp_path / "Pelicula.es.srt")

    respuesta = client.post("/folders", json={"ruta": str(fichero)})

    assert respuesta.status_code == 400


def test_alta_duplicada_devuelve_409(client: TestClient, tmp_path: Path) -> None:
    client.post("/folders", json={"ruta": str(tmp_path)})

    respuesta = client.post("/folders", json={"ruta": str(tmp_path)})

    assert respuesta.status_code == 409


def test_alta_de_una_subcarpeta_devuelve_409(client: TestClient, tmp_path: Path) -> None:
    hija = tmp_path / "series"
    hija.mkdir()
    client.post("/folders", json={"ruta": str(tmp_path)})

    respuesta = client.post("/folders", json={"ruta": str(hija)})

    assert respuesta.status_code == 409
    assert "superior" in respuesta.json()["detail"]


def test_alta_de_una_carpeta_superior_devuelve_409(client: TestClient, tmp_path: Path) -> None:
    hija = tmp_path / "series"
    hija.mkdir()
    client.post("/folders", json={"ruta": str(hija)})

    respuesta = client.post("/folders", json={"ruta": str(tmp_path)})

    assert respuesta.status_code == 409
    assert "subcarpeta" in respuesta.json()["detail"]


def test_dos_carpetas_hermanas_conviven(client: TestClient, tmp_path: Path) -> None:
    for nombre in ("series", "peliculas"):
        (tmp_path / nombre).mkdir()
        assert client.post("/folders", json={"ruta": str(tmp_path / nombre)}).status_code == 201

    assert len(client.get("/folders").json()) == 2


def test_desmarcar_no_borra_los_subtitulos(
    client: TestClient, db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    escribir_srt(tmp_path / "Pelicula.es.srt")
    (fila,) = registrar_carpetas(tmp_path)
    client.post("/scan")

    respuesta = client.patch(f"/folders/{fila.id}", json={"activa": False})

    assert respuesta.status_code == 200
    assert respuesta.json()["activa"] is False
    assert respuesta.json()["num_subtitulos"] == 1
    assert len(db.scalars(select(ArchivoSubtitulo)).all()) == 1


def test_los_contadores_reflejan_el_estado(
    client: TestClient, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    escribir_srt(tmp_path / "Pendiente.es.srt")
    escribir_srt(tmp_path / "Traducida.es.srt")
    escribir_srt(tmp_path / "Traducida.ES-KO.bilingue.srt")
    escribir_srt(tmp_path / "Rota.es.srt", "esto no es un subtítulo")
    registrar_carpetas(tmp_path)
    client.post("/scan")

    carpeta = client.get("/folders").json()[0]

    assert carpeta["num_subtitulos"] == 3
    assert carpeta["num_dual"] == 1
    assert carpeta["num_pendientes"] == 1
    assert carpeta["num_errores"] == 1
    assert carpeta["ultimo_escaneo"] is not None


def test_borrar_la_carpeta_arrastra_sus_subtitulos(
    client: TestClient, db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    escribir_srt(tmp_path / "Pelicula.es.srt")
    (fila,) = registrar_carpetas(tmp_path)
    client.post("/scan")

    respuesta = client.delete(f"/folders/{fila.id}")

    assert respuesta.status_code == 204
    assert client.get("/folders").json() == []
    assert db.scalars(select(ArchivoSubtitulo)).all() == []


def test_operar_sobre_una_carpeta_inexistente_devuelve_404(client: TestClient) -> None:
    assert client.patch("/folders/999", json={"activa": False}).status_code == 404
    assert client.delete("/folders/999").status_code == 404

"""Tests del explorador de disco (`/fs`) que alimenta el selector de carpetas."""

from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import escribir_srt


def test_roots_devuelve_al_menos_un_punto_de_partida(client: TestClient) -> None:
    respuesta = client.get("/fs/roots")

    assert respuesta.status_code == 200
    raices = respuesta.json()
    assert raices
    assert all(Path(raiz["ruta"]).exists() for raiz in raices)


def test_browse_lista_los_subdirectorios_ordenados(client: TestClient, tmp_path: Path) -> None:
    for nombre in ("zeta", "alfa", "Beta"):
        (tmp_path / nombre).mkdir()

    respuesta = client.get("/fs/browse", params={"ruta": str(tmp_path)})

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert [d["nombre"] for d in datos["directorios"]] == ["alfa", "Beta", "zeta"]
    assert datos["ruta"] == str(tmp_path.resolve())
    assert datos["padre"] == str(tmp_path.resolve().parent)


def test_browse_no_lista_ficheros(client: TestClient, tmp_path: Path) -> None:
    escribir_srt(tmp_path / "Pelicula.es.srt")
    (tmp_path / "series").mkdir()

    respuesta = client.get("/fs/browse", params={"ruta": str(tmp_path)})

    assert [d["nombre"] for d in respuesta.json()["directorios"]] == ["series"]


def test_browse_omite_los_ocultos(client: TestClient, tmp_path: Path) -> None:
    (tmp_path / ".oculta").mkdir()
    (tmp_path / "visible").mkdir()

    respuesta = client.get("/fs/browse", params={"ruta": str(tmp_path)})

    assert [d["nombre"] for d in respuesta.json()["directorios"]] == ["visible"]


def test_browse_de_una_ruta_inexistente_devuelve_404(client: TestClient, tmp_path: Path) -> None:
    respuesta = client.get("/fs/browse", params={"ruta": str(tmp_path / "no-existe")})

    assert respuesta.status_code == 404


def test_browse_de_un_fichero_devuelve_404(client: TestClient, tmp_path: Path) -> None:
    fichero = escribir_srt(tmp_path / "Pelicula.es.srt")

    respuesta = client.get("/fs/browse", params={"ruta": str(fichero)})

    assert respuesta.status_code == 404


def test_browse_sin_ruta_devuelve_422(client: TestClient) -> None:
    respuesta = client.get("/fs/browse")

    assert respuesta.status_code == 422

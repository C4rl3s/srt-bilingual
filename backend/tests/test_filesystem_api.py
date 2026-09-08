"""Tests del explorador de disco (`/fs`) que alimenta el selector de carpetas."""

import subprocess
import sys
from pathlib import Path

import pytest
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


def test_browse_marca_las_entradas_como_accesibles(client: TestClient, tmp_path: Path) -> None:
    """Una carpeta normal se lista como accesible y sin motivo de fallo."""
    (tmp_path / "normal").mkdir()

    respuesta = client.get("/fs/browse", params={"ruta": str(tmp_path)})

    (entrada,) = respuesta.json()["directorios"]
    assert entrada["accesible"] is True
    assert entrada["motivo"] is None


def _crear_enlace_roto(enlace: Path, destino: Path) -> bool:
    """Crea un enlace de directorio a un destino que no existe.

    Reproduce el caso real que motivó este test: las *junctions* de un recurso
    compartido que apuntan a una ruta del otro equipo. Desde aquí figuran en el
    listado del padre como directorio, pero no se pueden abrir.
    """
    try:
        enlace.symlink_to(destino, target_is_directory=True)
        return True
    except OSError:
        pass

    if sys.platform == "win32":
        # `mklink /J` crea una junction y, a diferencia de los enlaces simbólicos,
        # no exige privilegios de administrador.
        completado = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(enlace), str(destino)],
            capture_output=True,
            check=False,
        )
        return completado.returncode == 0

    return False


def test_browse_lista_un_enlace_roto_como_inaccesible(client: TestClient, tmp_path: Path) -> None:
    """Un enlace que no se puede seguir debe aparecer marcado, no desaparecer.

    Cuidado con el detalle que hizo fallar la primera versión: `os.scandir` reutiliza
    los atributos del listado del padre, así que `DirEntry.is_dir()` dice `True` sin
    seguir el enlace. Solo un `stat` nuevo revela que no se puede abrir.
    """
    enlace = tmp_path / "enlace"
    if not _crear_enlace_roto(enlace, tmp_path / "destino-que-no-existe"):
        pytest.skip("este equipo no permite crear enlaces de directorio")

    respuesta = client.get("/fs/browse", params={"ruta": str(tmp_path)})

    (entrada,) = respuesta.json()["directorios"]
    assert entrada["nombre"] == "enlace"
    assert entrada["accesible"] is False
    assert entrada["motivo"]


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

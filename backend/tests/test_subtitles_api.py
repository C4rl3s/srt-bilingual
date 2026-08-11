"""Tests de los endpoints `GET /subtitles`, `GET /subtitles/{id}` y `POST /scan`."""

from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import EstadoSubtitulo, Idioma
from app.models.library_folder import CarpetaBiblioteca
from app.models.subtitle_file import ArchivoSubtitulo
from tests.conftest import escribir_srt


def _sembrar(db: Session) -> None:
    """Inserta una carpeta con tres subtítulos de estados e idiomas distintos."""
    carpeta = CarpetaBiblioteca(ruta="/media")
    db.add(carpeta)
    db.flush()
    db.add_all(
        [
            ArchivoSubtitulo(
                carpeta=carpeta,
                ruta="/media/Pelicula.es.srt",
                nombre="Pelicula.es.srt",
                idioma_origen=Idioma.ES,
                estado=EstadoSubtitulo.PENDING,
                num_caracteres=100,
                num_bloques=10,
                mtime=1.0,
                tamano_bytes=200,
            ),
            ArchivoSubtitulo(
                carpeta=carpeta,
                ruta="/media/Otra.es.srt",
                nombre="Otra.es.srt",
                idioma_origen=Idioma.ES,
                estado=EstadoSubtitulo.TRANSLATED,
                ruta_bilingue="/media/Otra.ES-KO.bilingue.srt",
                idioma_destino=Idioma.KO,
                num_caracteres=50,
                num_bloques=5,
                mtime=1.0,
                tamano_bytes=100,
            ),
            ArchivoSubtitulo(
                carpeta=carpeta,
                ruta="/media/Serie.en.srt",
                nombre="Serie.en.srt",
                idioma_origen=Idioma.EN,
                estado=EstadoSubtitulo.PENDING,
                num_caracteres=30,
                num_bloques=3,
                mtime=1.0,
                tamano_bytes=60,
            ),
        ]
    )
    db.commit()


def test_listar_sin_datos_devuelve_lista_vacia(client: TestClient) -> None:
    respuesta = client.get("/subtitles")

    assert respuesta.status_code == 200
    assert respuesta.json() == []


def test_listar_devuelve_los_subtitulos_ordenados_por_ruta(client: TestClient, db: Session) -> None:
    _sembrar(db)

    respuesta = client.get("/subtitles")

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert [s["nombre"] for s in datos] == ["Otra.es.srt", "Pelicula.es.srt", "Serie.en.srt"]
    assert datos[0]["num_caracteres"] == 50
    assert datos[0]["ruta_bilingue"] == "/media/Otra.ES-KO.bilingue.srt"


def test_listar_filtra_por_estado(client: TestClient, db: Session) -> None:
    _sembrar(db)

    respuesta = client.get("/subtitles", params={"estado": "PENDING"})

    assert respuesta.status_code == 200
    nombres = [s["nombre"] for s in respuesta.json()]
    assert nombres == ["Pelicula.es.srt", "Serie.en.srt"]


def test_listar_filtra_por_idioma(client: TestClient, db: Session) -> None:
    _sembrar(db)

    respuesta = client.get("/subtitles", params={"idioma": "EN"})

    assert [s["nombre"] for s in respuesta.json()] == ["Serie.en.srt"]


def test_listar_con_filtro_invalido_devuelve_422(client: TestClient) -> None:
    respuesta = client.get("/subtitles", params={"estado": "INVENTADO"})

    assert respuesta.status_code == 422


def test_obtener_subtitulo_por_id(client: TestClient, db: Session) -> None:
    _sembrar(db)
    id_esperado = client.get("/subtitles").json()[0]["id"]

    respuesta = client.get(f"/subtitles/{id_esperado}")

    assert respuesta.status_code == 200
    assert respuesta.json()["nombre"] == "Otra.es.srt"


def test_obtener_subtitulo_inexistente_devuelve_404(client: TestClient) -> None:
    respuesta = client.get("/subtitles/999")

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "Subtítulo no encontrado"


def test_scan_inventaria_y_devuelve_resumen(
    client: TestClient, tmp_path: Path, registrar_carpetas: Callable[..., list[CarpetaBiblioteca]]
) -> None:
    escribir_srt(tmp_path / "Pelicula.es.srt")
    registrar_carpetas(tmp_path)

    respuesta = client.post("/scan")

    assert respuesta.status_code == 200
    resumen = respuesta.json()
    assert resumen["carpetas"] == 1
    assert resumen["nuevos"] == 1
    assert resumen["total"] == 1

    # Y el inventario queda consultable por la API.
    listado = client.get("/subtitles").json()
    assert len(listado) == 1
    assert listado[0]["nombre"] == "Pelicula.es.srt"
    assert listado[0]["idioma_origen"] == "ES"
    assert listado[0]["num_caracteres"] == 18


def test_scan_con_carpeta_ids_escanea_solo_esas(
    client: TestClient, tmp_path: Path, registrar_carpetas: Callable[..., list[CarpetaBiblioteca]]
) -> None:
    carpeta_a = tmp_path / "a"
    carpeta_b = tmp_path / "b"
    escribir_srt(carpeta_a / "Pelicula.es.srt")
    escribir_srt(carpeta_b / "Otra.es.srt")
    fila_a, _ = registrar_carpetas(carpeta_a, carpeta_b)

    respuesta = client.post("/scan", json={"carpeta_ids": [fila_a.id]})

    assert respuesta.status_code == 200
    assert respuesta.json()["carpetas"] == 1
    assert [s["nombre"] for s in client.get("/subtitles").json()] == ["Pelicula.es.srt"]

"""Tests del árbol de la biblioteca (`/library/tree` y `services/library_tree`)."""

from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import EstadoSubtitulo
from app.models.library_folder import CarpetaBiblioteca
from app.schemas.tree import EstadoObra
from app.services.library_tree import construir_arbol
from app.services.scanner import escanear
from tests.conftest import escribir_srt, escribir_video

Registrar = Callable[..., list[CarpetaBiblioteca]]


def _serie_de_prueba(raiz: Path) -> None:
    """Una serie con dos capítulos; el primero traducido y en dos idiomas."""
    temporada = raiz / "Breaking Bad" / "Season 1"
    escribir_srt(temporada / "BB.S01E01.es.srt")
    escribir_srt(temporada / "BB.S01E01.en.srt")
    escribir_srt(temporada / "BB.S01E01.ES-KO.bilingue.srt")
    escribir_srt(temporada / "BB.S01E02.es.srt")


def test_el_arbol_llega_hasta_la_obra(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    _serie_de_prueba(tmp_path)
    registrar_carpetas(tmp_path)
    escanear(db)

    (raiz,) = construir_arbol(db)

    serie = raiz.hijos[0]
    temporada = serie.hijos[0]
    assert serie.nombre == "Breaking Bad"
    assert temporada.nombre == "Season 1"
    assert [nodo.nombre for nodo in temporada.hijos] == ["BB.S01E01", "BB.S01E02"]
    assert all(nodo.hoja for nodo in temporada.hijos)


def test_los_idiomas_de_un_capitulo_se_agrupan_en_una_hoja(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    _serie_de_prueba(tmp_path)
    registrar_carpetas(tmp_path)
    escanear(db)

    (raiz,) = construir_arbol(db)
    capitulo = raiz.hijos[0].hijos[0].hijos[0]

    # Dos ficheros (.es y .en), una sola hoja.
    assert len(capitulo.subtitulo_ids) == 2
    assert sorted(idioma.value for idioma in capitulo.idiomas) == ["EN", "ES"]
    assert capitulo.dual is True
    assert capitulo.ruta_bilingue is not None
    assert capitulo.num_caracteres == 36  # 18 por fichero


def test_los_agregados_suben_por_las_ramas(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    _serie_de_prueba(tmp_path)
    registrar_carpetas(tmp_path)
    escanear(db)

    (raiz,) = construir_arbol(db)

    assert raiz.num_obras == 2
    assert raiz.num_dual == 1
    assert raiz.num_errores == 0
    assert raiz.hijos[0].num_obras == 2  # la serie entera


def test_los_errores_se_cuentan_en_su_rama(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    escribir_srt(tmp_path / "pelis" / "Rota.es.srt", "esto no es un subtítulo")
    registrar_carpetas(tmp_path)
    escanear(db)

    (raiz,) = construir_arbol(db)

    assert raiz.num_errores == 1
    assert raiz.hijos[0].hijos[0].nombre == "Rota"


def test_filtrar_por_estado_poda_las_ramas_vacias(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    _serie_de_prueba(tmp_path)
    escribir_srt(tmp_path / "pelis" / "Otra.es.srt")  # rama solo con pendientes
    registrar_carpetas(tmp_path)
    escanear(db)

    (raiz,) = construir_arbol(db, estado=EstadoSubtitulo.TRANSLATED)

    # Solo sobrevive la rama del capítulo traducido; `pelis` desaparece entera.
    assert [nodo.nombre for nodo in raiz.hijos] == ["Breaking Bad"]
    assert raiz.num_obras == 1
    assert raiz.hijos[0].hijos[0].hijos[0].nombre == "BB.S01E01"


def test_un_video_sin_subtitulos_aparece_como_hoja(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    """El caso de una biblioteca con los subtítulos embebidos en el MKV."""
    escribir_video(tmp_path / "Gunbuster" / "Gunbuster - 01.mkv")
    escribir_video(tmp_path / "Gunbuster" / "Gunbuster - 02.mkv")
    registrar_carpetas(tmp_path)
    escanear(db)

    (raiz,) = construir_arbol(db)

    serie = raiz.hijos[0]
    assert [nodo.nombre for nodo in serie.hijos] == ["Gunbuster - 01", "Gunbuster - 02"]
    assert all(nodo.estado_obra is EstadoObra.SIN_SUBTITULOS for nodo in serie.hijos)
    assert all(nodo.tiene_video for nodo in serie.hijos)
    assert raiz.num_obras == 2
    assert raiz.num_sin_subtitulos == 2
    assert raiz.num_dual == 0


def test_el_video_y_su_subtitulo_hermano_son_una_sola_hoja(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    escribir_video(tmp_path / "Cap01.mkv")
    escribir_srt(tmp_path / "Cap01.es.srt")
    registrar_carpetas(tmp_path)
    escanear(db)

    (raiz,) = construir_arbol(db)

    (hoja,) = raiz.hijos
    assert hoja.nombre == "Cap01"
    assert hoja.tiene_video is True
    assert hoja.estado_obra is EstadoObra.PENDIENTE
    assert len(hoja.subtitulo_ids) == 1


def test_el_estado_dual_gana_al_video(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    escribir_video(tmp_path / "Cap01.mkv")
    escribir_srt(tmp_path / "Cap01.es.srt")
    escribir_srt(tmp_path / "Cap01.ES-KO.bilingue.srt")
    registrar_carpetas(tmp_path)
    escanear(db)

    (raiz,) = construir_arbol(db)

    (hoja,) = raiz.hijos
    assert hoja.estado_obra is EstadoObra.DUAL
    assert hoja.tiene_video is True


def test_filtrar_por_estado_deja_fuera_los_videos_sin_subtitulos(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    escribir_video(tmp_path / "SinSubs.mkv")
    escribir_video(tmp_path / "ConSubs.mkv")
    escribir_srt(tmp_path / "ConSubs.es.srt")
    registrar_carpetas(tmp_path)
    escanear(db)

    (raiz,) = construir_arbol(db, estado=EstadoSubtitulo.PENDING)

    assert [nodo.nombre for nodo in raiz.hijos] == ["ConSubs"]


def test_una_carpeta_sin_subtitulos_sigue_apareciendo(
    db: Session, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    registrar_carpetas(tmp_path)

    (raiz,) = construir_arbol(db)

    assert raiz.hijos == []
    assert raiz.num_obras == 0


def test_el_endpoint_devuelve_el_arbol(
    client: TestClient, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    _serie_de_prueba(tmp_path)
    registrar_carpetas(tmp_path)
    client.post("/scan")

    respuesta = client.get("/library/tree")

    assert respuesta.status_code == 200
    (raiz,) = respuesta.json()
    assert raiz["num_obras"] == 2
    assert raiz["num_dual"] == 1
    capitulo = raiz["hijos"][0]["hijos"][0]["hijos"][0]
    assert capitulo["hoja"] is True
    assert capitulo["dual"] is True


def test_el_endpoint_filtra_por_carpeta(
    client: TestClient, tmp_path: Path, registrar_carpetas: Registrar
) -> None:
    carpeta_a = tmp_path / "a"
    carpeta_b = tmp_path / "b"
    escribir_srt(carpeta_a / "Pelicula.es.srt")
    escribir_srt(carpeta_b / "Otra.es.srt")
    fila_a, _ = registrar_carpetas(carpeta_a, carpeta_b)
    client.post("/scan")

    respuesta = client.get("/library/tree", params={"carpeta_id": fila_a.id})

    (raiz,) = respuesta.json()
    assert raiz["ruta"] == str(carpeta_a)
    assert [nodo["nombre"] for nodo in raiz["hijos"]] == ["Pelicula"]

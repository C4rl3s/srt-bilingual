"""Tests del parser de `.srt`: parseo, conteo y detección de idioma."""

from datetime import timedelta
from pathlib import Path

import pytest

from app.models.enums import Idioma
from app.services.subtitles import srt_parser
from tests.conftest import SRT_EJEMPLO, escribir_srt


def test_parsear_devuelve_bloques_normalizados(tmp_path: Path) -> None:
    ruta = escribir_srt(tmp_path / "pelicula.es.srt")

    bloques = srt_parser.parsear(ruta)

    assert len(bloques) == 2
    assert bloques[0].indice == 1
    assert bloques[0].inicio == timedelta(seconds=1)
    assert bloques[0].fin == timedelta(seconds=3)
    assert bloques[0].contenido == "Hola, mundo."
    assert bloques[1].contenido == "Adiós."


def test_contar_caracteres_ignora_indices_y_tiempos(tmp_path: Path) -> None:
    ruta = escribir_srt(tmp_path / "pelicula.es.srt")

    bloques = srt_parser.parsear(ruta)

    # Solo el texto: "Hola, mundo." (12) + "Adiós." (6).
    assert srt_parser.contar_caracteres(bloques) == 18


def test_contar_caracteres_incluye_las_lineas_de_un_bloque_multilinea(tmp_path: Path) -> None:
    contenido = "1\n00:00:01,000 --> 00:00:03,000\nPrimera\nSegunda\n"
    ruta = escribir_srt(tmp_path / "multi.es.srt", contenido)

    bloques = srt_parser.parsear(ruta)

    # "Primera\nSegunda" = 7 + 1 (salto) + 7.
    assert srt_parser.contar_caracteres(bloques) == 15


def test_contar_bloques(tmp_path: Path) -> None:
    ruta = escribir_srt(tmp_path / "pelicula.es.srt")

    assert srt_parser.contar_bloques(srt_parser.parsear(ruta)) == 2


def test_parsear_lee_ficheros_con_bom(tmp_path: Path) -> None:
    ruta = tmp_path / "bom.es.srt"
    ruta.write_bytes(b"\xef\xbb\xbf" + SRT_EJEMPLO.encode("utf-8"))

    bloques = srt_parser.parsear(ruta)

    # Sin gestionar el BOM, el primer índice no parsearía.
    assert bloques[0].indice == 1
    assert bloques[0].contenido == "Hola, mundo."


def test_parsear_recurre_a_latin1_si_no_es_utf8(tmp_path: Path) -> None:
    ruta = tmp_path / "latino.es.srt"
    ruta.write_bytes(SRT_EJEMPLO.encode("latin-1"))

    bloques = srt_parser.parsear(ruta)

    assert bloques[1].contenido == "Adiós."


def test_parsear_lanza_excepcion_si_esta_malformado(tmp_path: Path) -> None:
    ruta = escribir_srt(tmp_path / "roto.es.srt", "esto no es un subtítulo válido")

    with pytest.raises(Exception):
        srt_parser.parsear(ruta)


@pytest.mark.parametrize(
    ("nombre", "esperado"),
    [
        ("Pelicula.es.srt", Idioma.ES),
        ("Pelicula.ES.srt", Idioma.ES),  # el sufijo no distingue mayúsculas
        ("Pelicula.spa.srt", Idioma.ES),
        ("Pelicula.spanish.srt", Idioma.ES),
        ("Pelicula.eng.srt", Idioma.EN),
        ("Pelicula.ko.srt", Idioma.KO),
        ("Pelicula.es.forced.srt", Idioma.ES),  # flags ignorados
        ("Pelicula.en.sdh.srt", Idioma.EN),
        ("Pelicula.srt", Idioma.UNKNOWN),  # sin sufijo de idioma
        ("It.2017.srt", Idioma.UNKNOWN),  # no confundir el título con un idioma
    ],
)
def test_detectar_idioma_desde_nombre(nombre: str, esperado: Idioma) -> None:
    assert srt_parser.detectar_idioma_desde_nombre(nombre) is esperado

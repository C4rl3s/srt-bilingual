"""Tests de la convención de nombre del subtítulo bilingüe."""

from pathlib import Path

import pytest

from app.models.enums import Idioma
from app.services.subtitles.naming import derivar_nombre_bilingue, es_fichero_bilingue


@pytest.mark.parametrize(
    ("origen", "esperado"),
    [
        ("Pelicula.es.srt", "Pelicula.ES-KO.bilingue.srt"),  # quita el sufijo de idioma
        ("Pelicula.spa.srt", "Pelicula.ES-KO.bilingue.srt"),  # y también sus variantes
        ("Pelicula.srt", "Pelicula.ES-KO.bilingue.srt"),  # sin sufijo, igual de válido
        ("It.2017.es.srt", "It.2017.ES-KO.bilingue.srt"),  # el punto del título se respeta
    ],
)
def test_derivar_nombre_bilingue(origen: str, esperado: str) -> None:
    resultado = derivar_nombre_bilingue(Path(origen), Idioma.ES, Idioma.KO)

    assert resultado.name == esperado


def test_derivar_nombre_bilingue_mantiene_la_carpeta(tmp_path: Path) -> None:
    origen = tmp_path / "series" / "Cap01.es.srt"

    resultado = derivar_nombre_bilingue(origen, Idioma.ES, Idioma.KO)

    assert resultado.parent == origen.parent


def test_derivar_nombre_bilingue_refleja_el_par_de_idiomas() -> None:
    resultado = derivar_nombre_bilingue(Path("Pelicula.en.srt"), Idioma.EN, Idioma.JA)

    assert resultado.name == "Pelicula.EN-JA.bilingue.srt"


@pytest.mark.parametrize(
    ("nombre", "esperado"),
    [
        ("Pelicula.ES-KO.bilingue.srt", True),
        ("Pelicula.es.srt", False),
        ("Pelicula.srt", False),
        ("Pelicula.bilingue.txt", False),
    ],
)
def test_es_fichero_bilingue(nombre: str, esperado: bool) -> None:
    assert es_fichero_bilingue(nombre) is esperado


def test_el_bilingue_derivado_se_reconoce_como_bilingue() -> None:
    """Invariante clave: lo que genera el sistema, el escáner lo excluye."""
    derivado = derivar_nombre_bilingue(Path("Pelicula.es.srt"), Idioma.ES, Idioma.KO)

    assert es_fichero_bilingue(derivado.name)

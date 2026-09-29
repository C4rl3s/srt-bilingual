"""Tests de la guía de traducción (`srt-bilingual.toml`): dónde se busca y qué admite."""

from pathlib import Path

import pytest

from app.services.translation.base import ErrorTraduccion
from app.services.translation.guia import (
    MAX_INSTRUCCIONES,
    MAX_LARGO_INSTRUCCION,
    NOMBRE_FICHERO,
    GuiaInvalida,
    buscar,
    guia_de,
    leer,
)

GUIA = """
# Guía de Shingeki
[glosario]
"Marley" = "마레"
"titán acorazado" = "갑옷 거인"
"isla Paradis" = "파라디 섬"
"Isla Paradis" = "파라디 섬"

[instrucciones]
lista = [
  "Korean subtitles for Attack on Titan.",
  "'ustedes' is plural 'you', not formal: 너희.",
]
"""


def _escribir(carpeta: Path, contenido: str = GUIA) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / NOMBRE_FICHERO
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


# --- Dónde se busca ---


def test_sin_fichero_no_hay_guia(tmp_path: Path) -> None:
    capitulo = tmp_path / "Anime" / "Shingeki" / "S4"
    capitulo.mkdir(parents=True)

    assert guia_de(capitulo, tmp_path / "Anime") is None


def test_la_de_la_serie_vale_para_sus_temporadas(tmp_path: Path) -> None:
    raiz = tmp_path / "Anime"
    ruta = _escribir(raiz / "Shingeki")
    temporada = raiz / "Shingeki" / "Shingeki no Kyojin S4 Pt. 1"
    temporada.mkdir()

    assert buscar(temporada, raiz) == ruta


def test_gana_la_mas_cercana(tmp_path: Path) -> None:
    raiz = tmp_path / "Anime"
    _escribir(raiz / "Shingeki")
    propia = _escribir(raiz / "Shingeki" / "S4")

    assert buscar(raiz / "Shingeki" / "S4", raiz) == propia


def test_la_de_la_propia_raiz_cuenta(tmp_path: Path) -> None:
    raiz = tmp_path / "Anime"
    ruta = _escribir(raiz)
    (raiz / "Serie").mkdir()

    assert buscar(raiz / "Serie", raiz) == ruta


def test_no_sube_por_encima_de_la_raiz(tmp_path: Path) -> None:
    _escribir(tmp_path)  # fuera de la carpeta de biblioteca
    serie = tmp_path / "Anime" / "Serie"
    serie.mkdir(parents=True)

    assert buscar(serie, tmp_path / "Anime") is None


def test_una_carpeta_fuera_de_la_raiz_no_tiene_guia(tmp_path: Path) -> None:
    _escribir(tmp_path / "Otra")

    assert buscar(tmp_path / "Otra", tmp_path / "Anime") is None


# --- Qué se lee ---


def test_lee_glosario_e_instrucciones(tmp_path: Path) -> None:
    guia = leer(_escribir(tmp_path))

    assert guia.glosario["Marley"] == "마레"
    assert guia.glosario["titán acorazado"] == "갑옷 거인"
    assert guia.instrucciones == (
        "Korean subtitles for Attack on Titan.",
        "'ustedes' is plural 'you', not formal: 너희.",
    )


def test_las_variantes_de_mayusculas_se_conservan(tmp_path: Path) -> None:
    # El glosario de DeepL distingue mayúsculas: hacen falta las dos.
    guia = leer(_escribir(tmp_path))

    assert {"isla Paradis", "Isla Paradis"} <= set(guia.glosario)


def test_basta_con_glosario_o_con_instrucciones(tmp_path: Path) -> None:
    solo_glosario = leer(_escribir(tmp_path / "a", '[glosario]\n"Marley" = "마레"\n'))
    solo_instrucciones = leer(_escribir(tmp_path / "b", '[instrucciones]\nlista = ["Sé breve."]\n'))

    assert solo_glosario.instrucciones == ()
    assert solo_instrucciones.glosario == {}


def test_quita_espacios_sobrantes(tmp_path: Path) -> None:
    guia = leer(_escribir(tmp_path, '[glosario]\n" Marley " = " 마레 "\n'))

    assert guia.glosario == {"Marley": "마레"}


def test_la_huella_no_cambia_con_comentarios_ni_orden(tmp_path: Path) -> None:
    a = leer(_escribir(tmp_path / "a", '[glosario]\n"A" = "가"\n"B" = "나"\n'))
    b = leer(_escribir(tmp_path / "b", '# otro comentario\n[glosario]\n"B" = "나"\n"A" = "가"\n'))

    assert a.huella == b.huella


def test_la_huella_cambia_con_el_contenido(tmp_path: Path) -> None:
    a = leer(_escribir(tmp_path / "a", '[glosario]\n"Marley" = "마레"\n'))
    b = leer(_escribir(tmp_path / "b", '[glosario]\n"Marley" = "말리"\n'))
    c = leer(
        _escribir(tmp_path / "c", '[glosario]\n"Marley" = "마레"\n[instrucciones]\nlista = ["x"]\n')
    )

    assert len({a.huella, b.huella, c.huella}) == 3


# --- Qué se rechaza ---


@pytest.mark.parametrize(
    ("contenido", "motivo"),
    [
        ('[glosario\n"Marley" = "마레"\n', "TOML"),
        ('[glossario]\n"Marley" = "마레"\n', "desconocidas"),
        ('glosario = "Marley"\n', "tabla"),
        ('[glosario]\n"Marley" = 3\n', "texto"),
        ('[glosario]\n"Marley" = "  "\n', "vacía"),
        ('[glosario]\n"Mar\\tley" = "마레"\n', "tabuladores"),
        ('[instrucciones]\ntexto = ["x"]\n', "lista"),
        ('[instrucciones]\nlista = "x"\n', "lista de textos"),
        ('[instrucciones]\nlista = [""]\n', "vacía"),
        ("", "vacía"),
    ],
)
def test_rechaza_guias_mal_escritas(tmp_path: Path, contenido: str, motivo: str) -> None:
    with pytest.raises(GuiaInvalida, match=motivo):
        leer(_escribir(tmp_path, contenido))


def test_limite_de_instrucciones(tmp_path: Path) -> None:
    lista = ", ".join(f'"instrucción {n}"' for n in range(MAX_INSTRUCCIONES + 1))

    with pytest.raises(GuiaInvalida, match=f"máximo es {MAX_INSTRUCCIONES}"):
        leer(_escribir(tmp_path, f"[instrucciones]\nlista = [{lista}]\n"))


def test_limite_de_largo_de_una_instruccion(tmp_path: Path) -> None:
    larga = "x" * (MAX_LARGO_INSTRUCCION + 1)

    with pytest.raises(GuiaInvalida, match="instrucción 1"):
        leer(_escribir(tmp_path, f'[instrucciones]\nlista = ["{larga}"]\n'))


def test_el_error_nombra_el_fichero_y_es_un_error_de_traduccion(tmp_path: Path) -> None:
    # Un trabajo que se tope con una guía rota falla con el motivo, no la ignora.
    _escribir(tmp_path, "[glosario\n")

    with pytest.raises(ErrorTraduccion, match=NOMBRE_FICHERO):
        guia_de(tmp_path, tmp_path)

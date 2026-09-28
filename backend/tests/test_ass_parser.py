"""Tests del parser ASS: el diálogo sale limpio y los carteles y el karaoke, fuera.

El ASS de ejemplo reproduce lo visto en las pistas reales: la cabecera y los estilos
de *Shingeki* (Erai-raws), las etiquetas `{\\an8}` e `{\\i1}` de *Moonrise* (Netflix)
y los carteles, dibujos y karaoke habituales en los fansubs.
"""

from datetime import timedelta
from pathlib import Path

import pytest

from app.services.subtitles.ass_parser import ErrorAss, es_dialogo, limpiar, parsear, parsear_texto

ASS = """﻿[Script Info]
Title: Shingeki no Kyojin - 01
ScriptType: v4.00+
PlayResX: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, Bold, Italic, Alignment, MarginV
Style: Default,Trebuchet MS,45,&H00FFFFFF,-1,0,2,15
Style: Sign_Default,Arial,40,&H00FFFFFF,0,0,8,10
Style: OP_Romaji,Arial,40,&H00FFFFFF,0,0,8,10

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:04:50.84,0:04:53.09,Default,M,0,0,0,,¿Por qué lloras, Eren?
Dialogue: 0,0:04:43.20,0:04:44.81,Default,E,0,0,0,,¿Qué pasaba?
Comment: 0,0:04:44.00,0:04:45.00,Default,,0,0,0,,nota del traductor
Dialogue: 0,0:05:05.98,0:05:08.77,Default,Priest,0,0,0,,Dios construyó las murallas\\Ncon su sabiduría.
Dialogue: 0,0:02:22.14,0:02:23.35,Default,,0,0,0,,{\\an8}Hermana, ¿cómo vas?
Dialogue: 0,0:02:57.67,0:02:58.88,Default,,0,0,0,,{\\i1}Aplicar grabado.{\\i0}
Dialogue: 0,0:06:00.00,0:06:02.00,Sign_Default,,0,0,0,,Información pública actualmente
Dialogue: 0,0:06:10.00,0:06:12.00,Default,,0,0,0,,{\\pos(960,200)}DISTRITO DE TROST
Dialogue: 0,0:06:20.00,0:06:22.00,Default,,0,0,0,,{\\p1}m 0 0 l 100 0 100 100 0 100{\\p0}
Dialogue: 0,0:01:00.00,0:01:04.00,OP_Romaji,,0,0,0,,{\\k20}Guren {\\k30}no {\\k40}yumiya
Dialogue: 0,0:01:05.00,0:01:08.00,Default,,0,0,0,,{\\k20}Se{\\k30}ño{\\k40}res
Dialogue: 1,0:07:00.00,0:07:02.00,Default,,0,0,0,,¡Atención!
Dialogue: 0,0:07:00.00,0:07:02.00,Default,,0,0,0,,{\\bord3}¡Atención!
Dialogue: 0,0:07:05.00,0:07:06.00,Default,,0,0,0,,{\\fad(200,200)}
"""


def test_saca_el_dialogo_ordenado_y_limpio() -> None:
    bloques = parsear_texto(ASS)

    assert [b.contenido for b in bloques] == [
        "Hermana, ¿cómo vas?",
        "Aplicar grabado.",
        "¿Qué pasaba?",
        "¿Por qué lloras, Eren?",  # la coma del texto no rompe los campos
        "Dios construyó las murallas\ncon su sabiduría.",
        "¡Atención!",  # dos capas del mismo texto: una sola vez
    ]
    assert [b.indice for b in bloques] == [1, 2, 3, 4, 5, 6]
    assert bloques[0].inicio == timedelta(minutes=2, seconds=22, milliseconds=140)
    assert bloques[0].fin == timedelta(minutes=2, seconds=23, milliseconds=350)


@pytest.mark.parametrize(
    ("estilo", "texto", "dialogo"),
    [
        ("Default", "Hola", True),
        ("Default - italics", "{\\i1}Hola{\\i0}", True),
        ("Title", "{\\fad(1,807)}Año 845", True),  # el título del episodio se queda
        ("Sign_Default", "Cartel", False),
        ("SignA", "Cartel", False),
        ("Typeset", "Cartel", False),
        ("Cart_A_Tre", "Club de ocultismo", False),
        ("Cartel", "Cartel", False),
        ("Cartman", "Respect my authoritah", True),
        ("EndCard", "Ilustración", False),
        ("OP", "Letra", False),
        ("ED_English", "Letra", False),
        ("Opening-Romaji", "Letra", False),
        ("Kanji", "歌", False),
        ("Default", "{\\pos(960,200)}Cartel", False),
        ("Default", "{\\move(0,0,100,100)}Cartel", False),
        ("Default", "{\\p1}m 0 0 l 1 1", False),
        ("Default", "{\\k20}Sí{\\k30}la{\\k40}ba", False),
        ("Default", "{\\kf20}Sí{\\ko30}la", False),
        ("Edward", "Nombre de personaje, no ending", True),
    ],
)
def test_que_es_dialogo(estilo: str, texto: str, dialogo: bool) -> None:
    assert es_dialogo(estilo, texto) is dialogo


def test_limpiar_etiquetas_saltos_y_espacios_duros() -> None:
    assert limpiar("{\\an8}{\\i1}Uno\\NDos\\hy{\\i0}  tres ") == "Uno\nDos y tres"
    assert limpiar("{\\c&H00FF00&}") == ""


def test_lee_el_fichero_con_bom(tmp_path: Path) -> None:
    ruta = tmp_path / "pista.ass"
    ruta.write_text(ASS, encoding="utf-8")

    assert len(parsear(ruta)) == 6


def test_sin_eventos_es_un_error() -> None:
    with pytest.raises(ErrorAss):
        parsear_texto("[Script Info]\nTitle: vacío\n")


def test_una_marca_de_tiempo_rota_es_un_error() -> None:
    roto = "[Events]\nFormat: Layer, Start, End, Style, Text\nDialogue: 0,ayer,0:00:02.00,Default,Hola\n"
    with pytest.raises(ErrorAss):
        parsear_texto(roto)

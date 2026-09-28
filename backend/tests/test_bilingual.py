"""Tests del generador de bilingües: los tiempos del origen se conservan intactos."""

from datetime import timedelta
from pathlib import Path

import pytest

from app.models.enums import Idioma
from app.services import bilingual
from app.services.bilingual import ErrorGeneracion
from app.services.subtitles import srt_parser
from app.services.subtitles.alineacion import alinear
from app.services.subtitles.modelo import Bloque
from app.services.subtitles.naming import es_fichero_bilingue, ruta_bilingue_de_obra
from tests.conftest import TraductorFalso, escribir_srt

# Numeración que no empieza en 1 y con un salto: el bilingüe debe respetarla tal cual.
ORIGEN_SRT = """5
00:01:23,400 --> 00:01:25,900
- ¿Cómo era tu nombre?
- Chrissie.

6
00:01:26,000 --> 00:01:27,250
<i>Espera.</i>

9
00:01:30,017 --> 00:01:33,480
No estoy borracho. ¡Espera!
"""


def _origen(tmp_path: Path) -> list[Bloque]:
    return srt_parser.parsear(escribir_srt(tmp_path / "Jaws.es.srt", ORIGEN_SRT))


def test_cada_bloque_lleva_el_original_y_debajo_el_coreano(tmp_path: Path) -> None:
    bloques = _origen(tmp_path)

    compuestos = bilingual.componer(bloques, ["- 이름이 뭐였지?\n- 크리시.", "잠깐.", "안 취했어!"])

    assert (
        compuestos[0].contenido
        == "- ¿Cómo era tu nombre?\n- Chrissie.\n- 이름이 뭐였지?\n- 크리시."
    )
    assert compuestos[1].contenido == "<i>Espera.</i>\n잠깐."


def test_un_bloque_sin_coreano_se_queda_solo_con_el_original(tmp_path: Path) -> None:
    """En la fusión, las frases que el coreano no traduce llegan como cadena vacía."""
    compuestos = bilingual.componer(_origen(tmp_path), ["이름?", "", "안 취했어!"])

    assert compuestos[1].contenido == "<i>Espera.</i>"


def test_rechaza_textos_que_no_encajan_con_los_bloques(tmp_path: Path) -> None:
    with pytest.raises(ErrorGeneracion, match="2 textos coreanos para 3 bloques"):
        bilingual.componer(_origen(tmp_path), ["uno", "dos"])


def test_el_bilingue_conserva_indices_y_tiempos_exactos(tmp_path: Path) -> None:
    """La razón de ser del proyecto: releído del disco, el bilingüe tiene los mismos
    índices y las mismas marcas de tiempo, al milisegundo, que el original."""
    origen = _origen(tmp_path)
    destino = tmp_path / "Jaws.ES-KO.bilingue.srt"

    bilingual.generar(origen, ["이름?", "잠깐.", "안 취했어!"], destino)

    releido = srt_parser.parsear(destino)
    assert [(b.indice, b.inicio, b.fin) for b in releido] == [
        (b.indice, b.inicio, b.fin) for b in origen
    ]
    assert [b.indice for b in releido] == [5, 6, 9]  # sin renumerar
    assert releido[2].contenido.splitlines() == ["No estoy borracho. ¡Espera!", "안 취했어!"]


def test_se_escribe_en_utf8(tmp_path: Path) -> None:
    destino = tmp_path / "Jaws.ES-KO.bilingue.srt"

    bilingual.generar(_origen(tmp_path), ["이름?", "잠깐.", "안 취했어!"], destino)

    assert "안 취했어!" in destino.read_bytes().decode("utf-8")


def test_funciona_con_la_salida_de_un_traductor(tmp_path: Path) -> None:
    """Modo traducción: el generador no distingue de dónde viene el coreano."""
    origen = _origen(tmp_path)
    textos = TraductorFalso().traducir([b.contenido for b in origen], Idioma.ES, Idioma.KO)

    destino = bilingual.generar(origen, textos, tmp_path / "a.ES-KO.bilingue.srt")

    assert srt_parser.parsear(destino)[2].contenido.endswith("[KO] No estoy borracho. ¡Espera!")


def test_funciona_con_la_salida_de_la_alineacion(tmp_path: Path) -> None:
    """Modo fusión: el coreano llega con otros cortes y medio segundo de desfase."""
    origen = _origen(tmp_path)
    coreano = [
        Bloque(1, timedelta(seconds=83.9), timedelta(seconds=86.4), "- 이름이 뭐였지?\n- 크리시."),
        Bloque(2, timedelta(seconds=90.5), timedelta(seconds=94.0), "난 안 취했어!"),
    ]

    destino = bilingual.generar(origen, alinear(origen, coreano).textos, tmp_path / "b.srt")

    releido = srt_parser.parsear(destino)
    assert [(b.inicio, b.fin) for b in releido] == [(b.inicio, b.fin) for b in origen]
    assert releido[1].contenido == "<i>Espera.</i>"  # sin coreano: solo el original
    assert releido[2].contenido.endswith("난 안 취했어!")


def test_escritura_atomica_si_falla_no_deja_nada_a_medias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un fallo a mitad no deja ni el temporal ni un bilingüe truncado, y un bilingüe
    anterior sigue intacto."""
    destino = tmp_path / "Jaws.ES-KO.bilingue.srt"
    destino.write_text("bilingüe anterior", encoding="utf-8")

    def falla(*_args) -> None:
        raise OSError("la unidad de red se ha desconectado")

    monkeypatch.setattr(bilingual.os, "replace", falla)

    with pytest.raises(OSError):
        bilingual.generar(_origen(tmp_path), ["a", "b", "c"], destino)

    assert destino.read_text(encoding="utf-8") == "bilingüe anterior"
    assert [p.name for p in tmp_path.iterdir() if p.suffix == ".tmp"] == []


def test_el_bilingue_de_una_obra_va_junto_al_video_con_su_nombre(tmp_path: Path) -> None:
    ruta = ruta_bilingue_de_obra(tmp_path / "Jaws (1975)", "Jaws.1975.1080p", Idioma.EN)

    assert ruta == tmp_path / "Jaws (1975)" / "Jaws.1975.1080p.EN-KO.bilingue.srt"
    assert es_fichero_bilingue(ruta.name)  # el escáner no lo tomará como origen

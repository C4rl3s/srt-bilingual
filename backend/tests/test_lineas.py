"""Tests de cómo se envían las líneas de un bloque a traducir y cómo vuelve el coreano.

Los casos son los de la prueba de calidad de la Fase 5 (*Moonrise* 01).
"""

import pytest

from app.services.subtitles.lineas import (
    LARGO_PARA_PARTIR,
    es_dialogo,
    para_traducir,
    partir_en_dos,
    recolocar,
)


def test_una_frase_partida_en_dos_lineas_se_envia_entera() -> None:
    bloque = "Concluyen ya los festejos por el proyecto\ndel eje orbital de Sapientia,"

    assert para_traducir(bloque) == (
        "Concluyen ya los festejos por el proyecto del eje orbital de Sapientia,"
    )


def test_con_etiquetas_y_espacios_sobrantes() -> None:
    assert para_traducir("<i>Noventa segundos </i>\n <i>para atracar.</i>") == (
        "<i>Noventa segundos </i> <i>para atracar.</i>"
    )


@pytest.mark.parametrize(
    "bloque",
    [
        "- ¡Vamos!\n- ¿Qué? Espera…",
        "- Justo a tiempo.\n- Atrás, señor.",
        "<i>- ¡Largo!</i>\n<i>- ¡La Luna es nuestra!</i>",
        "– Raya larga\n– también cuenta",
    ],
)
def test_un_dialogo_se_envia_con_sus_lineas(bloque: str) -> None:
    assert es_dialogo(bloque)
    assert para_traducir(bloque) == bloque


def test_una_linea_con_guion_sola_no_es_dialogo() -> None:
    assert not es_dialogo("- ¡Corred!")
    assert not es_dialogo("¡Hola!\n- ¿Qué?")  # solo si todas llevan guion


def test_el_coreano_largo_vuelve_en_dos_lineas() -> None:
    original = "Noventa segundos\npara atracar en el Eje Orbital E40."
    coreano = "E40 궤도 축에 도킹하기까지 90초 남았습니다."

    assert recolocar(original, coreano) == "E40 궤도 축에 도킹하기까지\n90초 남았습니다."


def test_el_coreano_corto_se_queda_en_una_linea() -> None:
    corto = "고칠 시간이 없어."
    assert len(corto) < LARGO_PARA_PARTIR

    assert recolocar("No hay tiempo para arreglarlo.\nToca defenderse.", corto) == corto


def test_si_el_original_era_de_una_linea_no_se_parte() -> None:
    largo = "그리고 이 자리를 빌려 대학 졸업 후 이사로 취임할 제 아들을 소개하고자 합니다"

    assert recolocar("Una sola línea muy larga del original", largo) == largo


def test_un_dialogo_vuelve_como_lo_dio_el_proveedor() -> None:
    assert recolocar("- ¡Vamos!\n- ¿Qué? Espera…", "- 가자!\n- 뭐? 잠깐…") == "- 가자!\n- 뭐? 잠깐…"


def test_quita_los_signos_de_apertura_del_espanol() -> None:
    # Caso real (S4 Pt. 1-07): el proveedor dejó «¡피크!» en una frase muy corta.
    assert recolocar("¡Pieck!", "¡피크!") == "피크!"
    assert recolocar("-¿Zeke?\n-¡Pieck!", "-¿지크?\n-¡피크!") == "-지크?\n-피크!"


def test_partir_en_dos_por_el_espacio_mas_centrado() -> None:
    assert partir_en_dos("우리는 함께 완성을 축하합니다") == "우리는 함께\n완성을 축하합니다"


def test_sin_espacios_no_se_parte() -> None:
    texto = "띄어쓰기없는아주긴한국어문장입니다"

    assert partir_en_dos(texto) == texto


def test_nunca_deja_una_linea_vacia() -> None:
    for texto in ("가 나다라마바사아자차카타파하", " 앞에공백", "뒤에공백 "):
        assert all(partir_en_dos(texto).split("\n"))

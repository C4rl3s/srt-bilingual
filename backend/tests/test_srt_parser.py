"""Tests del parser de `.srt`: parseo, conteo y detección de idioma."""

from datetime import timedelta
from pathlib import Path

import pytest

from app.models.enums import Idioma
from app.services.subtitles import srt_parser
from app.services.subtitles.modelo import Bloque
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


@pytest.mark.parametrize(
    ("nombre", "idioma", "forzado", "sdh"),
    [
        # Patrón RARBG: el idioma va tras un guion bajo.
        ("2_English.srt", Idioma.EN, False, False),
        ("5_Spanish.srt", Idioma.ES, False, False),
        # Flags entre paréntesis o corchetes, no solo entre puntos.
        ("Latin American (Forced).spa.srt", Idioma.ES, True, False),
        ("Spanish [SDH].spa.srt", Idioma.ES, False, True),
        ("English (CC).eng.srt", Idioma.EN, False, True),
        ("SDH.eng.HI.srt", Idioma.EN, False, True),
        ("Forced.eng.srt", Idioma.EN, True, False),
        # Idioma separado por un espacio.
        ("Stalker.1979.1080p.BluRay.x264.AAC-[YTS.MX] ENG.srt", Idioma.EN, False, False),
        # Un `hi` que es parte del título, no del sufijo, no es un flag SDH.
        ("Hi.Mom.2021.srt", Idioma.UNKNOWN, False, False),
        # El nombre de la película no se confunde con el idioma del subtítulo.
        ("The.Wailing.2016.KOREAN.1080p.BluRay.x265-VXT.srt", Idioma.UNKNOWN, False, False),
        ("Pelicula.1080p.WEBRip.x264.AAC5.1-[YTS.MX].srt", Idioma.UNKNOWN, False, False),
    ],
)
def test_analizar_nombre(nombre: str, idioma: Idioma, forzado: bool, sdh: bool) -> None:
    info = srt_parser.analizar_nombre(nombre)

    assert info.idioma is idioma
    assert info.es_forzado is forzado
    assert info.es_sdh is sdh


# --- Detección por contenido ---------------------------------------------------------

TEXTO_ES = (
    "¿Qué haces aquí? No lo sé, pero tengo que irme ahora.",
    "Ella está con él en la casa de los vecinos.",
    "Eso es muy raro. ¿Por qué no me lo dijiste cuando llegaste?",
    "Porque yo también estoy cansado de todo esto.",
    "Hay algo que usted tiene que saber sobre las cartas.",
    "Ya está bien. Vamos al coche, que se hace tarde.",
)
TEXTO_EN = (
    "What are you doing here? I don't know, but I have to go now.",
    "She is with him at the house of the neighbors.",
    "That is so weird. Why didn't you tell me when you got here?",
    "Because I'm tired of all this too, you know.",
    "There is something you have to know about the letters.",
    "It's all right. Just get in the car, it's getting late.",
)
TEXTO_KO = (
    "여기서 뭐 하는 거야? 모르겠어, 이제 가야 해.",
    "그녀는 이웃집에 그와 함께 있어.",
    "정말 이상하네. 왜 도착했을 때 말 안 했어?",
)
# Francés: comparte alfabeto y alguna palabra con el español, pero no debe pasar
# por español.
TEXTO_FR = (
    "Qu'est-ce que tu fais ici? Je ne sais pas, mais je dois partir maintenant.",
    "Elle est avec lui dans la maison des voisins.",
    "C'est très bizarre. Pourquoi tu ne me l'as pas dit quand tu es arrivé?",
    "Parce que je suis fatigué de tout ça aussi.",
    "Il y a quelque chose que vous devez savoir sur les lettres.",
    "Ça suffit. Allons à la voiture, il se fait tard.",
)


def _bloques(lineas: tuple[str, ...], repeticiones: int = 3) -> list[Bloque]:
    """Bloques consecutivos de 2 s con las líneas dadas, repetidas para tener muestra."""
    return [
        Bloque(
            indice=i + 1,
            inicio=timedelta(seconds=2 * i),
            fin=timedelta(seconds=2 * i + 1),
            contenido=linea,
        )
        for i, linea in enumerate(lineas * repeticiones)
    ]


@pytest.mark.parametrize(
    ("lineas", "esperado"),
    [
        (TEXTO_ES, Idioma.ES),
        (TEXTO_EN, Idioma.EN),
        (TEXTO_KO, Idioma.KO),
        (TEXTO_FR, Idioma.UNKNOWN),
    ],
)
def test_detectar_idioma_desde_contenido(lineas: tuple[str, ...], esperado: Idioma) -> None:
    assert srt_parser.detectar_idioma_desde_contenido(_bloques(lineas)) is esperado


def test_poco_texto_no_basta_para_decidir() -> None:
    """Un `.srt` con solo el anuncio de YTS no tiene muestra suficiente."""
    bloques = _bloques(("Downloaded from YTS.MX", "Official YIFY movies site"), 1)

    assert srt_parser.detectar_idioma_desde_contenido(bloques) is Idioma.UNKNOWN


def test_las_etiquetas_de_formato_no_cuentan_como_palabras() -> None:
    """Sin quitarlas, cada `<i>` sumaría como la palabra inglesa `i`."""
    lineas = tuple(f"<i>{linea}</i>" for linea in TEXTO_ES)

    assert srt_parser.detectar_idioma_desde_contenido(_bloques(lineas)) is Idioma.ES


def test_el_contenido_manda_sobre_un_nombre_que_miente() -> None:
    """Caso real: `It Ends\\Subs\\spa.srt` es inglés de principio a fin."""
    assert srt_parser.detectar_idioma("spa.srt", _bloques(TEXTO_EN)) is Idioma.EN


def test_si_el_contenido_no_decide_vale_el_nombre() -> None:
    """Un forzado de pocas líneas no da para decidir: se respeta lo que dice el nombre."""
    bloques = _bloques(("¿Qué?", "Hola."), 1)

    assert srt_parser.detectar_idioma("Forced.spa.srt", bloques) is Idioma.ES


def test_parsear_lee_coreano_en_cp949(tmp_path: Path) -> None:
    """Caso real: el `.ko.srt` de *Backrooms* no es UTF-8 sino CP949."""
    contenido = "1\n00:01:22,166 --> 00:01:24,585\n좋아, 좋아...\n"
    ruta = tmp_path / "pelicula.ko.srt"
    ruta.write_bytes(contenido.encode("cp949"))

    bloques = srt_parser.parsear(ruta)

    assert bloques[0].contenido == "좋아, 좋아..."

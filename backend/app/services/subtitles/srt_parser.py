"""Parser de ficheros `.srt` y utilidades de conteo / detección de idioma.

Convierte el `.srt` a la representación normalizada `Bloque`, de forma que el resto
del dominio no dependa de la librería `srt`.

El idioma se deduce primero del **nombre** (barato y fiable cuando lo declara) y,
solo si el nombre no dice nada, del **contenido** ya parseado.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import srt

from app.models.enums import SUFIJOS_IDIOMA, TOKENS_FLAG, TOKENS_FORZADO, TOKENS_SDH, Idioma
from app.services.subtitles.modelo import Bloque


def leer_texto(ruta: Path) -> str:
    """Lee el fichero como texto manejando BOM y las codificaciones heredadas que
    aparecen en la biblioteca real: CP949 en subtítulos coreanos y latin-1 en los
    europeos antiguos. La usa también el parser de ASS."""
    datos = ruta.read_bytes()
    try:
        return datos.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    # CP949 solo se acepta si decodifica sin errores **y** el resultado es coreano: un
    # texto latino casi nunca pasa la decodificación estricta, pero si pasara por
    # casualidad saldría una ensalada de caracteres sin apenas hangul.
    try:
        texto = datos.decode("cp949")
    except UnicodeDecodeError:
        pass
    else:
        if _proporcion_hangul(texto) >= UMBRAL_HANGUL:
            return texto
    return datos.decode("latin-1")


def parsear(ruta: Path) -> list[Bloque]:
    """Parsea un `.srt` y devuelve sus subtítulos como `list[Bloque]`.

    Lanza excepción si el contenido está malformado (lo gestiona el scanner).
    """
    contenido = leer_texto(ruta)
    return [
        Bloque(indice=sub.index, inicio=sub.start, fin=sub.end, contenido=sub.content)
        for sub in srt.parse(contenido)
    ]


def contar_caracteres(bloques: list[Bloque]) -> int:
    """Caracteres de texto (sin índices ni marcas de tiempo), espacios incluidos."""
    return sum(len(bloque.contenido.strip()) for bloque in bloques)


def contar_bloques(bloques: list[Bloque]) -> int:
    """Número de subtítulos (cues) del fichero."""
    return len(bloques)


# --- Detección por nombre ---------------------------------------------------------

# Separadores de tokens en un nombre de fichero. No solo el punto: `2_English.srt`
# (RARBG) o `Latin American (Forced).spa.srt` esconden el idioma o el flag tras `_`,
# espacios o paréntesis.
_SEPARADORES_NOMBRE = re.compile(r"[.\s_\-\[\]()]+")


@dataclass(frozen=True, slots=True)
class InfoNombre:
    """Lo que el nombre de un subtítulo dice de sí mismo."""

    idioma: Idioma
    es_forzado: bool
    es_sdh: bool


def analizar_nombre(nombre: str) -> InfoNombre:
    """Lee idioma y flags del **sufijo** del nombre.

    Recorre los tokens de derecha a izquierda mientras sean flags (`forced`, `sdh`…)
    o un código de idioma, y se detiene en el primero que no es ninguna de las dos
    cosas. Así `SDH.eng.HI.srt` → EN + SDH, pero `Hi.Mom.2021.srt` no se toma por SDH
    (el `hi` es parte del título, no del sufijo) e `It.2017.srt` no se toma por
    italiano.
    """
    tronco = nombre[: -len(".srt")] if nombre.lower().endswith(".srt") else nombre
    tokens = [token.lower() for token in _SEPARADORES_NOMBRE.split(tronco) if token]

    idioma = Idioma.UNKNOWN
    es_forzado = False
    es_sdh = False
    for token in reversed(tokens):
        if token in TOKENS_FLAG:
            es_forzado = es_forzado or token in TOKENS_FORZADO
            es_sdh = es_sdh or token in TOKENS_SDH
        elif idioma is Idioma.UNKNOWN and token in SUFIJOS_IDIOMA:
            idioma = SUFIJOS_IDIOMA[token]
        else:
            break
    return InfoNombre(idioma=idioma, es_forzado=es_forzado, es_sdh=es_sdh)


def detectar_idioma_desde_nombre(nombre: str) -> Idioma:
    """Idioma declarado en el nombre, o `UNKNOWN` si no declara ninguno."""
    return analizar_nombre(nombre).idioma


# --- Detección por contenido ------------------------------------------------------

# Palabras muy frecuentes y propias de cada idioma. Se evitan a propósito las que
# comparten ES y EN (`a`, `no`, `me`, `he`) y las más habituales en portugués,
# italiano o francés (`de`, `que`, `la`), para que un fichero en otro idioma no
# sume puntos por accidente.
STOPWORDS_ES: frozenset[str] = frozenset(
    {
        "el", "los", "las", "y", "es", "está", "pero", "qué", "por", "para", "con",
        "una", "lo", "su", "muy", "yo", "eso", "esto", "esta", "cómo", "aquí", "nada",
        "bien", "hay", "ya", "sí", "usted", "estoy", "tengo", "puedo", "porque",
        "también", "cuando", "dónde", "ahora", "ella", "él", "del", "al", "mi", "tu",
    }
)  # fmt: skip
STOPWORDS_EN: frozenset[str] = frozenset(
    {
        "the", "and", "you", "is", "that", "it", "what", "to", "of", "i", "this",
        "was", "have", "don't", "not", "are", "we", "with", "be", "my", "your", "for",
        "on", "just", "know", "there", "they", "can", "i'm", "it's", "he's", "do",
        "get", "all", "about", "right", "here", "him", "her", "his",
    }
)  # fmt: skip

# Marcas de formato que no son texto: etiquetas HTML (`<i>`) y overrides de ASS
# (`{\an8}`). Sin quitarlas, cada `<i>` contaría como la palabra inglesa `i`.
_MARCAS_FORMATO = re.compile(r"<[^>]*>|\{[^}]*\}")
# Palabras: letras, con apóstrofo interno opcional (`don't`).
_PALABRA = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?")

# Por debajo de este número de palabras no hay muestra suficiente para decidir
# (p. ej. un `.srt` que solo trae el anuncio de YTS).
MIN_PALABRAS = 50
# Fracción mínima de palabras que deben ser stopwords del idioma ganador. Calibrado
# sobre los 686 `.srt` de la biblioteca real: el ES/EN completo más pobre da 0,11
# (un SDH lleno de acotaciones) y ningún otro idioma pasa de 0,07 (el polaco, cuyos
# `i`, `to` y `on` coinciden con palabras inglesas).
UMBRAL_DENSIDAD = 0.10
# El ganador debe sacar al otro al menos esta ventaja (en número de stopwords).
VENTAJA_MINIMA = 3.0
# Fracción de letras en hangul a partir de la cual el texto es coreano.
UMBRAL_HANGUL = 0.3


def _es_hangul(caracter: str) -> bool:
    """Sílabas y jamo del alfabeto coreano."""
    return "가" <= caracter <= "힣" or "ᄀ" <= caracter <= "ᇿ"


def _proporcion_hangul(texto: str) -> float:
    """Fracción de las letras del texto que son hangul (0 si no hay letras)."""
    letras = [c for c in texto if c.isalpha()]
    if not letras:
        return 0.0
    return sum(_es_hangul(c) for c in letras) / len(letras)


def detectar_idioma_desde_contenido(bloques: list[Bloque]) -> Idioma:
    """Deduce el idioma del texto: `KO`, `ES`, `EN` o `UNKNOWN`.

    El coreano se reconoce por el alfabeto, sin estadística. Español e inglés, por
    la densidad de sus palabras más frecuentes. Si ninguno destaca con claridad
    devuelve `UNKNOWN` en vez de inventarse un ganador: un origen equivocado da un
    bilingüe inservible, y uno desconocido solo deja la obra pendiente.
    """
    texto = _MARCAS_FORMATO.sub(" ", "\n".join(bloque.contenido for bloque in bloques))

    if _proporcion_hangul(texto) >= UMBRAL_HANGUL:
        return Idioma.KO

    # El apóstrofo tipográfico (`don’t`) se unifica con el recto de las stopwords.
    palabras = _PALABRA.findall(texto.lower().replace("’", "'"))
    if len(palabras) < MIN_PALABRAS:
        return Idioma.UNKNOWN

    marcas_es = sum(palabra in STOPWORDS_ES for palabra in palabras)
    marcas_en = sum(palabra in STOPWORDS_EN for palabra in palabras)
    for idioma, propias, ajenas in (
        (Idioma.ES, marcas_es, marcas_en),
        (Idioma.EN, marcas_en, marcas_es),
    ):
        if propias / len(palabras) >= UMBRAL_DENSIDAD and propias >= VENTAJA_MINIMA * ajenas:
            return idioma
    return Idioma.UNKNOWN


def detectar_idioma(nombre: str, bloques: list[Bloque]) -> Idioma:
    """Idioma del subtítulo combinando las dos fuentes.

    Manda el **contenido** cuando da un veredicto claro, y si no, el nombre. No es
    solo para los ficheros que no declaran idioma: en la biblioteca real hay un
    `spa.srt` que es inglés de principio a fin, y fiarse del nombre lo habría
    convertido en origen "español". Cuando el contenido no alcanza para decidir (un
    forzado de pocas líneas), el nombre sigue valiendo.
    """
    por_contenido = detectar_idioma_desde_contenido(bloques)
    if por_contenido is not Idioma.UNKNOWN:
        return por_contenido
    return detectar_idioma_desde_nombre(nombre)

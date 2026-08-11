"""Enumeraciones de dominio y mapeo de sufijos de idioma.

Los códigos de `Idioma` son canónicos y están alineados con los que usa DeepL
(Fase 3), de modo que el idioma detectado en Fase 1 se reutiliza sin traducción.
"""

from enum import Enum


class EstadoSubtitulo(str, Enum):
    """Estado de un fichero de subtítulos respecto a su versión bilingüe."""

    PENDING = "PENDING"  # parseado, sin versión bilingüe en disco
    TRANSLATED = "TRANSLATED"  # ya existe el .bilingue.srt (lo detecta el scanner)
    ERROR = "ERROR"  # falló el parseo


class FormatoSubtitulo(str, Enum):
    """Formato del fichero de subtítulos. Fase 1 solo soporta SRT; el enum deja la
    puerta abierta a VTT/ASS/SUB sin necesidad de migrar el esquema."""

    SRT = "SRT"


class Idioma(str, Enum):
    """Idiomas reconocidos, en códigos canónicos (alineados con DeepL)."""

    ES = "ES"
    EN = "EN"
    KO = "KO"
    FR = "FR"
    DE = "DE"
    IT = "IT"
    PT = "PT"
    JA = "JA"
    ZH = "ZH"
    UNKNOWN = "UNKNOWN"


# Sufijos reconocidos en los nombres de fichero (2 letras, 3 letras o nombre),
# normalizados a un `Idioma` canónico. Estilo Plex: `pelicula.spa.srt`.
SUFIJOS_IDIOMA: dict[str, Idioma] = {
    # Español
    "es": Idioma.ES,
    "spa": Idioma.ES,
    "esp": Idioma.ES,
    "spanish": Idioma.ES,
    "cas": Idioma.ES,
    "castellano": Idioma.ES,
    # Inglés
    "en": Idioma.EN,
    "eng": Idioma.EN,
    "english": Idioma.EN,
    # Coreano
    "ko": Idioma.KO,
    "kor": Idioma.KO,
    "korean": Idioma.KO,
    # Francés
    "fr": Idioma.FR,
    "fra": Idioma.FR,
    "fre": Idioma.FR,
    "french": Idioma.FR,
    # Alemán
    "de": Idioma.DE,
    "ger": Idioma.DE,
    "deu": Idioma.DE,
    "german": Idioma.DE,
    # Italiano
    "it": Idioma.IT,
    "ita": Idioma.IT,
    "italian": Idioma.IT,
    # Portugués
    "pt": Idioma.PT,
    "por": Idioma.PT,
    "portuguese": Idioma.PT,
    # Japonés
    "ja": Idioma.JA,
    "jpn": Idioma.JA,
    "japanese": Idioma.JA,
    # Chino
    "zh": Idioma.ZH,
    "chi": Idioma.ZH,
    "zho": Idioma.ZH,
    "chinese": Idioma.ZH,
}

# Tokens que a veces acompañan al idioma en el nombre y hay que ignorar al buscarlo
# (p. ej. `pelicula.es.forced.srt`).
TOKENS_FLAG: frozenset[str] = frozenset({"forced", "sdh", "cc", "hi"})

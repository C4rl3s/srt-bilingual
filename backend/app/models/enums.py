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


class ModoTrabajo(str, Enum):
    """De dónde sale el coreano del bilingüe."""

    TRADUCCION = "TRADUCCION"  # lo traduce un proveedor (DeepL…): gasta cuota
    FUSION = "FUSION"  # se alinea un subtítulo coreano que ya existía: no gasta cuota


class EstadoTrabajo(str, Enum):
    """Ciclo de vida de un trabajo de generación de bilingüe."""

    QUEUED = "QUEUED"  # creado, esperando a que lo recoja la tarea de fondo
    RUNNING = "RUNNING"  # en curso: `bloques_procesados` avanza
    DONE = "DONE"  # bilingüe escrito en disco
    FAILED = "FAILED"  # terminó con error: el motivo, en `mensaje_error`


class FormatoSubtitulo(str, Enum):
    """Formato del subtítulo: el del fichero externo (siempre SRT) o el códec de la
    pista incrustada en un vídeo (Fase 5)."""

    SRT = "SRT"
    ASS = "ASS"  # también SSA: con estilos y posicionamiento
    VTT = "VTT"
    MOV_TEXT = "MOV_TEXT"  # el texto de los MP4
    PGS = "PGS"  # imagen (Blu-ray)
    VOBSUB = "VOBSUB"  # imagen (DVD)


# Formatos que son imágenes de texto, no texto: sin OCR no se pueden leer, así que
# nunca sirven de origen ni de coreano (decisión de la Fase 5).
FORMATOS_IMAGEN: frozenset[FormatoSubtitulo] = frozenset(
    {FormatoSubtitulo.PGS, FormatoSubtitulo.VOBSUB}
)


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

# Código con que se escribe cada idioma al renombrar a la nomenclatura de Plex
# (`Pelicula.spa.srt`). ISO 639-2: Plex lo reconoce y es lo más habitual en la
# biblioteca real. Solo los idiomas con los que trabaja la app.
CODIGOS_PLEX: dict[Idioma, str] = {Idioma.ES: "spa", Idioma.EN: "eng", Idioma.KO: "kor"}

# Tokens que a veces acompañan al idioma en el nombre (p. ej. `pelicula.es.forced.srt`)
# y hay que saltar al buscarlo. Además de saltarlos, se anotan: un forzado (solo
# carteles) no sirve como origen, y un SDH (con descripciones sonoras) solo si no hay
# otro.
TOKENS_FORZADO: frozenset[str] = frozenset({"forced", "forzado", "forzados"})
TOKENS_SDH: frozenset[str] = frozenset({"sdh", "cc", "hi"})
TOKENS_FLAG: frozenset[str] = TOKENS_FORZADO | TOKENS_SDH

# Contenedores de vídeo que el escaneo inventaría. No se abren ni se parsean: se
# registran para poder dibujar la biblioteca aunque no haya ningún `.srt` al lado
# (caso habitual: los subtítulos viajan dentro del propio MKV).
EXTENSIONES_VIDEO: frozenset[str] = frozenset({".mkv", ".mp4", ".avi", ".m4v", ".mov"})

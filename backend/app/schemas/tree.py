"""DTOs del árbol de la biblioteca.

El árbol no se guarda en ninguna tabla: se **deriva** de las rutas de `media_file` y
`subtitle_file` cada vez que se pide (ver `services/library_tree.py`).
"""

from enum import Enum

from pydantic import BaseModel

from app.models.enums import Idioma


class EstadoObra(str, Enum):
    """Estado de un capítulo o película de cara a la interfaz.

    No es lo mismo que `EstadoSubtitulo`: aquel describe un fichero `.srt` suelto y
    este resume la obra entera, incluido el caso de no tener ningún subtítulo
    externo (lo normal cuando viajan dentro del MKV).
    """

    DUAL = "DUAL"  # ya existe el .bilingue.srt
    PENDIENTE = "PENDIENTE"  # tiene origen ES/EN válido: se le puede generar el bilingüe
    SIN_ORIGEN = "SIN_ORIGEN"  # tiene subtítulos, pero ninguno ES/EN válido como origen
    # Hay vídeo y ningún subtítulo: ni un .srt al lado ni pistas de texto dentro (o
    # aún no se han sondeado sus pistas).
    SIN_SUBTITULOS = "SIN_SUBTITULOS"
    ERROR = "ERROR"  # sin origen válido y con algún subtítulo que no se pudo parsear


class NodoArbol(BaseModel):
    """Nodo del árbol: una carpeta (`hoja=False`) o una obra (`hoja=True`).

    Modelo recursivo: `hijos` vuelve a ser una lista de `NodoArbol`. Pydantic v2
    resuelve la autorreferencia sin necesidad de `model_rebuild()` mientras el tipo
    se escriba entre comillas.
    """

    nombre: str
    ruta: str
    hoja: bool
    hijos: list["NodoArbol"] = []

    # Agregados (en las carpetas suman los de sus descendientes).
    num_obras: int = 0
    num_dual: int = 0
    num_errores: int = 0
    num_sin_subtitulos: int = 0
    num_sin_origen: int = 0

    # Solo en las hojas.
    estado_obra: EstadoObra | None = None
    tiene_video: bool = False
    idiomas: list[Idioma] = []
    dual: bool = False
    ruta_bilingue: str | None = None
    # Lo que costaría traducirla: lo mismo que reservaría el trabajo (ver
    # `trabajos.caracteres_previstos`). Si el origen es una pista sin extraer, es una
    # estimación (`caracteres_exactos = False`).
    num_caracteres: int = 0
    caracteres_exactos: bool = True
    # El origen propuesto es una pista incrustada en el vídeo, no un .srt.
    origen_en_video: bool = False
    subtitulo_ids: list[int] = []
    # Propuesta de la selección automática (ver `services/subtitles/seleccion.py`).
    subtitulo_origen_id: int | None = None
    idioma_origen: Idioma | None = None
    # Coreano ya existente: si lo hay, el bilingüe sale de fusionar, sin traducir.
    subtitulo_coreano_id: int | None = None
    # Guía de traducción de la serie que le toca, según el último escaneo (ver
    # `services/translation/guia.py`). Con ella se prefiere un proveedor que la admita.
    ruta_guia: str | None = None

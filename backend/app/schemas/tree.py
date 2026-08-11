"""DTOs del árbol de la biblioteca.

El árbol no se guarda en ninguna tabla: se **deriva** de las rutas de
`subtitle_file` cada vez que se pide (ver `services/library_tree.py`).
"""

from pydantic import BaseModel

from app.models.enums import Idioma


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

    # Solo en las hojas.
    idiomas: list[Idioma] = []
    dual: bool = False
    ruta_bilingue: str | None = None
    num_caracteres: int = 0
    subtitulo_ids: list[int] = []

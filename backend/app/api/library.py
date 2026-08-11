"""Router del árbol de la biblioteca."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.enums import EstadoSubtitulo
from app.schemas.tree import NodoArbol
from app.services import library_tree

router = APIRouter(tags=["library"])


@router.get("/library/tree", response_model=list[NodoArbol])
def arbol_biblioteca(
    db: Session = Depends(get_db),
    carpeta_id: int | None = Query(default=None),
    estado: EstadoSubtitulo | None = Query(default=None),
) -> list[NodoArbol]:
    """Árbol de carpetas hasta la obra, con los idiomas y el estado de cada una."""
    carpeta_ids = None if carpeta_id is None else [carpeta_id]
    return library_tree.construir_arbol(db, carpeta_ids=carpeta_ids, estado=estado)

"""Registro de proveedores: de un nombre a un `Translator` listo para usar.

Añadir un proveedor (Azure, Google…) es escribir su módulo en este paquete y una
línea en `_FABRICAS`. La Fase 4 hará que la elección dependa de la cuota libre de
cada uno; hoy manda `TRANSLATION_PROVIDER` del `.env`.
"""

from collections.abc import Callable

from app.config import settings
from app.services.translation.base import ProveedorNoDisponible, Translator
from app.services.translation.deepl_provider import TraductorDeepL


def _crear_deepl() -> Translator:
    if not settings.deepl_api_key:
        raise ProveedorNoDisponible("Falta DEEPL_API_KEY en backend/.env")
    return TraductorDeepL(settings.deepl_api_key)


# Fábricas y no instancias: un proveedor solo se construye (y solo se le exige su
# clave) si de verdad se va a usar.
_FABRICAS: dict[str, Callable[[], Translator]] = {
    "deepl": _crear_deepl,
}


def proveedores() -> list[str]:
    """Nombres de los proveedores que la app sabe usar."""
    return sorted(_FABRICAS)


def obtener_traductor(nombre: str | None = None) -> Translator:
    """El proveedor pedido, o el configurado en `TRANSLATION_PROVIDER` si no se pide
    ninguno."""
    clave = (nombre or settings.translation_provider).strip().lower()
    fabrica = _FABRICAS.get(clave)
    if fabrica is None:
        raise ProveedorNoDisponible(
            f"Proveedor de traducción desconocido: {clave!r}. Disponibles: {proveedores()}"
        )
    return fabrica()

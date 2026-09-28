"""Registro de proveedores: de un nombre a un `Translator` listo para usar.

Añadir un proveedor (Azure, Google…) es escribir su módulo en este paquete y una
línea en `_FABRICAS`. Qué proveedores se usan, y en qué orden de preferencia, lo dice
`TRANSLATION_PROVIDERS` en el `.env` (ver `Settings.proveedores`).
"""

from collections.abc import Callable

from app.config import settings
from app.services.translation.azure_provider import TraductorAzure
from app.services.translation.base import ProveedorNoDisponible, Translator
from app.services.translation.deepl_provider import TraductorDeepL


def _crear_deepl() -> Translator:
    if not settings.deepl_api_key:
        raise ProveedorNoDisponible("Falta DEEPL_API_KEY en backend/.env")
    return TraductorDeepL(settings.deepl_api_key)


def _crear_azure() -> Translator:
    if not settings.azure_translator_key:
        raise ProveedorNoDisponible("Falta AZURE_TRANSLATOR_KEY en backend/.env")
    return TraductorAzure(settings.azure_translator_key, settings.azure_translator_region)


# Fábricas y no instancias: un proveedor solo se construye (y solo se le exige su
# clave) si de verdad se va a usar.
_FABRICAS: dict[str, Callable[[], Translator]] = {
    "deepl": _crear_deepl,
    "azure": _crear_azure,
}

# Límite de los proveedores que no lo informan por su API: se compara con el
# registro de la app. Los que lo informan (DeepL) no necesitan entrada aquí.
_LIMITES: dict[str, Callable[[], int]] = {
    "azure": lambda: settings.azure_translator_limite_mensual,
}


def proveedores() -> list[str]:
    """Nombres de los proveedores que la app sabe usar."""
    return sorted(_FABRICAS)


def obtener_traductor(nombre: str | None = None) -> Translator:
    """El proveedor pedido, o el primero de la lista configurada si no se pide
    ninguno."""
    clave = (nombre or settings.proveedores[0]).strip().lower()
    fabrica = _FABRICAS.get(clave)
    if fabrica is None:
        raise ProveedorNoDisponible(
            f"Proveedor de traducción desconocido: {clave!r}. Disponibles: {proveedores()}"
        )
    return fabrica()


def limite_configurado(nombre: str) -> int | None:
    """Límite del periodo configurado para un proveedor, o `None` si no tiene."""
    limite = _LIMITES.get(nombre)
    return limite() if limite else None

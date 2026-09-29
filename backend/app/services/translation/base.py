"""Interfaz común de los proveedores de traducción.

El resto de la app solo conoce esto: el `Protocol` `Translator` y las excepciones de
aquí. Ningún fichero fuera de `services/translation/` importa el SDK de DeepL, así
que cambiar de proveedor cuando caduque una cuenta es añadir un módulo y una entrada
en `registry.py`, sin tocar nada más.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from app.models.enums import Idioma

if TYPE_CHECKING:
    # Solo para el tipo: `guia` importa este módulo (sus errores heredan de aquí).
    from app.services.translation.guia import Guia


@runtime_checkable
class Translator(Protocol):
    """Un proveedor de traducción.

    `Protocol` y no clase base abstracta: un proveedor cumple el contrato por tener
    estos miembros, sin heredar de nada (tipado estructural). Así un proveedor falso
    para los tests es una clase cualquiera con el mismo aspecto.

    **Invariante:** `traducir` devuelve exactamente un texto por texto recibido y en
    el mismo orden. Es lo que permite recomponer los bloques del bilingüe sin perder
    el emparejamiento. Quien llama lo verifica igualmente: no se fía del proveedor.
    """

    # Nombre con que se registra y se anota en `translation_job.proveedor`.
    nombre: str
    # Si aprovecha la guía de la serie (glosario e instrucciones). El que no, la recibe
    # y la ignora: la elección de proveedor y la interfaz usan esto para avisar.
    admite_guia: bool

    def traducir(
        self,
        textos: list[str],
        origen: Idioma,
        destino: Idioma,
        guia: Guia | None = None,
        contextos: list[str] | None = None,
    ) -> list[str]: ...

    # `contextos`: uno por texto (lo que lo rodea en el capítulo), solo si la guía lo
    # pide. Lo calcula quien llama porque el proveedor solo ve un lote de bloques.


@dataclass(frozen=True, slots=True)
class Consumo:
    """Caracteres gastados del cupo del proveedor en el periodo actual."""

    usados: int
    limite: int | None  # None: el proveedor no tiene límite (o no lo informa)


@runtime_checkable
class ConCupo(Protocol):
    """Proveedor que sabe decir cuánto cupo lleva gastado.

    Aparte de `Translator` a propósito: no todos los proveedores lo exponen, y la
    Fase 4 (elegir proveedor según su cupo libre) solo contará con los que sí.
    """

    def consumo(self) -> Consumo: ...


class ErrorTraduccion(Exception):
    """Fallo del proveedor que el trabajo registra en `mensaje_error`."""


class CuotaAgotada(ErrorTraduccion):
    """El proveedor rechaza la petición por cuota. Merece distinguirse: no se arregla
    reintentando, sino esperando al mes siguiente o cambiando de proveedor."""


class ProveedorNoDisponible(ErrorTraduccion):
    """El proveedor pedido no existe o no está configurado (falta su clave)."""

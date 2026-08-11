"""Representación interna normalizada de un subtítulo.

`Bloque` es el tipo común con el que trabaja todo el dominio (conteo y, en Fase 3,
generación bilingüe), independiente del formato de origen. El parser de cada
formato (hoy solo SRT) convierte sus estructuras a `list[Bloque]`, de modo que
añadir VTT/ASS en el futuro no obligue a tocar el resto del código.
"""

from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True, slots=True)
class Bloque:
    """Un subtítulo: índice, marca de inicio/fin y su texto (sin formato de fichero)."""

    indice: int
    inicio: timedelta
    fin: timedelta
    contenido: str

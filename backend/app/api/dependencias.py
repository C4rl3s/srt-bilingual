"""Dependencias de las tareas de fondo, compartidas por varios routers.

Existen para que los tests las sustituyan (`app.dependency_overrides`): una sesión
contra la BD de pruebas, un traductor que no llama a ningún proveedor, y un
`ffprobe` y un `ffmpeg` de pega que no abren vídeos. Viven aparte de los routers
porque varios las usan (el escaneo sondea, la generación extrae) y así ninguno tiene
que importar a otro.
"""

from app.db import SessionLocal
from app.services import trabajos
from app.services.mkv import extraccion, sondeo
from app.services.translation.registry import obtener_traductor


def get_fabrica_sesion() -> trabajos.FabricaSesion:
    return SessionLocal


def get_fabrica_traductor() -> trabajos.FabricaTraductor:
    return obtener_traductor


def get_sondeador() -> sondeo.Sondeador:
    return sondeo.ejecutar_ffprobe


def get_extractor() -> extraccion.Extractor:
    return extraccion.ejecutar_ffmpeg

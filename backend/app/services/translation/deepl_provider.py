"""Proveedor DeepL, con el SDK oficial (`deepl`).

El SDK ya reintenta con espera creciente ante cortes de red y respuestas 429 (hasta
5 veces), así que aquí no se programan reintentos propios: lo que llega como
excepción es un fallo de verdad.

**Guía de la serie** (`guia.py`): DeepL es el único proveedor que la aprovecha.

- El **glosario** se crea en la cuenta de DeepL con un nombre que identifica la guía
  y su contenido (`srt-bilingual:<guía>:<huella>:ES-KO`), y se reutiliza mientras el
  fichero no cambie. Al cambiar, se borra la versión anterior de esa misma guía.
  Crearlo no cuesta caracteres; hay un límite de 1000 por cuenta.
- Las **instrucciones** van en `custom_instructions`. Con ellas DeepL junta en una
  línea los diálogos con guion (comprobado en la prueba del 2026-09-29), así que
  entonces cada línea de un diálogo se traduce por separado.
"""

import hashlib
from collections.abc import Iterator

import deepl

from app.models.enums import Idioma
from app.services.translation.base import Consumo, CuotaAgotada, ErrorTraduccion
from app.services.translation.guia import IDIOMA_GLOSARIO, Guia

# Textos por petición. La API de DeepL limita el tamaño de la petición (128 KiB), no
# el número de textos; 50 bloques de subtítulo son unos 4 KB, muy lejos del límite.
# Una película de ~1500 bloques son ~30 peticiones en vez de 1500.
TAMANO_LOTE = 50

# Prefijo de los glosarios que crea la app: los demás de la cuenta no se tocan.
PREFIJO_GLOSARIO = "srt-bilingual"


class TraductorDeepL:
    """Implementa `Translator` sobre la API de DeepL."""

    nombre = "deepl"
    admite_guia = True

    def __init__(self, clave: str, cliente: deepl.Translator | None = None) -> None:
        # `cliente` permite inyectar uno falso en los tests. El SDK deduce el
        # servidor (cuenta con cupo o de pago) por el sufijo `:fx` de la clave.
        self._cliente = cliente or deepl.Translator(clave)
        # Glosarios de la cuenta, leídos al primer uso: nombre → glosario.
        self._glosarios: dict[str, deepl.GlossaryInfo] | None = None

    def traducir(
        self, textos: list[str], origen: Idioma, destino: Idioma, guia: Guia | None = None
    ) -> list[str]:
        opciones = self._opciones(guia, origen, destino)
        # Con instrucciones, cada línea de un diálogo va sola (ver cabecera). A este
        # punto un texto con varias líneas solo puede ser un diálogo: los demás bloques
        # llegan unidos en una frase (`subtitles/lineas.py`).
        separar = "custom_instructions" in opciones.get("extra_body_parameters", {})
        piezas = [texto.split("\n") if separar else [texto] for texto in textos]

        planos = self._traducir_planos(
            [p for lista in piezas for p in lista], origen, destino, opciones
        )
        traducidos, i = [], 0
        for lista in piezas:
            traducidos.append("\n".join(planos[i : i + len(lista)]))
            i += len(lista)
        return traducidos

    def consumo(self) -> Consumo:
        """Caracteres usados y límite del periodo, según DeepL."""
        try:
            caracteres = self._cliente.get_usage().character
        except deepl.DeepLException as exc:
            raise ErrorTraduccion(f"No se pudo consultar el cupo de DeepL: {exc}") from exc
        return Consumo(usados=caracteres.count, limite=caracteres.limit)

    def _traducir_planos(
        self, textos: list[str], origen: Idioma, destino: Idioma, opciones: dict
    ) -> list[str]:
        # DeepL rechaza los textos vacíos, y un bloque de subtítulo puede serlo: se
        # envían solo los que tienen contenido y se recolocan en su posición.
        con_texto = [i for i, texto in enumerate(textos) if texto.strip()]
        traducidos = list(textos)

        for lote in _lotes(con_texto, TAMANO_LOTE):
            resultados = self._pedir([textos[i] for i in lote], origen, destino, opciones)
            if len(resultados) != len(lote):
                raise ErrorTraduccion(
                    f"DeepL devolvió {len(resultados)} textos para {len(lote)} enviados"
                )
            for i, resultado in zip(lote, resultados, strict=True):
                traducidos[i] = resultado.text
        return traducidos

    def _opciones(self, guia: Guia | None, origen: Idioma, destino: Idioma) -> dict:
        """Parámetros extra de `translate_text` que salen de la guía."""
        if guia is None:
            return {}
        opciones: dict = {}
        if guia.glosario and origen is IDIOMA_GLOSARIO:
            opciones["glossary"] = self._glosario(guia, origen, destino)
        if guia.instrucciones:
            opciones["extra_body_parameters"] = {"custom_instructions": list(guia.instrucciones)}
        return opciones

    def _glosario(self, guia: Guia, origen: Idioma, destino: Idioma) -> deepl.GlossaryInfo:
        """El glosario de la guía en DeepL: el ya creado si no ha cambiado, o uno nuevo."""
        # La guía se identifica por su ruta; la versión, por la huella del contenido.
        familia = f"{PREFIJO_GLOSARIO}:{_id_ruta(guia)}:"
        nombre = f"{familia}{guia.huella}:{origen.value}-{destino.value}"
        glosarios = self._listar()
        if nombre in glosarios:
            return glosarios[nombre]

        try:
            # Versiones anteriores de esta misma guía: ya no se usarán.
            for viejo in [n for n in glosarios if n.startswith(familia)]:
                self._cliente.delete_glossary(glosarios.pop(viejo))
            nuevo = self._cliente.create_glossary(
                nombre, source_lang=origen.value, target_lang=destino.value, entries=guia.glosario
            )
        except deepl.DeepLException as exc:
            raise ErrorTraduccion(f"No se pudo preparar el glosario en DeepL: {exc}") from exc
        glosarios[nombre] = nuevo
        return nuevo

    def _listar(self) -> dict[str, deepl.GlossaryInfo]:
        if self._glosarios is None:
            try:
                self._glosarios = {
                    g.name: g
                    for g in self._cliente.list_glossaries()
                    if g.name.startswith(f"{PREFIJO_GLOSARIO}:")
                }
            except deepl.DeepLException as exc:
                raise ErrorTraduccion(f"No se pudieron leer los glosarios de DeepL: {exc}") from exc
        return self._glosarios

    def _pedir(self, textos: list[str], origen: Idioma, destino: Idioma, opciones: dict) -> list:
        try:
            resultado = self._cliente.translate_text(
                textos,
                source_lang=origen.value,
                target_lang=destino.value,
                # Respeta los saltos de línea y la puntuación del bloque original.
                preserve_formatting=True,
                **opciones,
            )
        except deepl.QuotaExceededException as exc:
            raise CuotaAgotada(f"Cuota de DeepL agotada: {exc}") from exc
        except deepl.AuthorizationException as exc:
            raise ErrorTraduccion(f"DeepL rechaza la clave (DEEPL_API_KEY): {exc}") from exc
        except deepl.DeepLException as exc:
            raise ErrorTraduccion(f"Error de DeepL: {exc}") from exc
        # Con una lista de textos el SDK devuelve una lista de resultados.
        return resultado if isinstance(resultado, list) else [resultado]


def _id_ruta(guia: Guia) -> str:
    """Identificador corto y estable de la guía por su ruta (sin distinguir
    mayúsculas: en Windows `Z:\\Anime` y `z:\\anime` son la misma carpeta)."""
    return hashlib.sha256(str(guia.ruta).casefold().encode("utf-8")).hexdigest()[:8]


def _lotes(indices: list[int], tamano: int) -> Iterator[list[int]]:
    for inicio in range(0, len(indices), tamano):
        yield indices[inicio : inicio + tamano]

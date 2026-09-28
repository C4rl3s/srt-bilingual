"""Proveedor DeepL, con el SDK oficial (`deepl`).

El SDK ya reintenta con espera creciente ante cortes de red y respuestas 429 (hasta
5 veces), así que aquí no se programan reintentos propios: lo que llega como
excepción es un fallo de verdad.
"""

from collections.abc import Iterator

import deepl

from app.models.enums import Idioma
from app.services.translation.base import Consumo, CuotaAgotada, ErrorTraduccion

# Textos por petición. La API de DeepL limita el tamaño de la petición (128 KiB), no
# el número de textos; 50 bloques de subtítulo son unos 4 KB, muy lejos del límite.
# Una película de ~1500 bloques son ~30 peticiones en vez de 1500.
TAMANO_LOTE = 50


class TraductorDeepL:
    """Implementa `Translator` sobre la API de DeepL."""

    nombre = "deepl"

    def __init__(self, clave: str, cliente: deepl.Translator | None = None) -> None:
        # `cliente` permite inyectar uno falso en los tests. El SDK deduce el
        # servidor (cuenta con cupo o de pago) por el sufijo `:fx` de la clave.
        self._cliente = cliente or deepl.Translator(clave)

    def traducir(self, textos: list[str], origen: Idioma, destino: Idioma) -> list[str]:
        # DeepL rechaza los textos vacíos, y un bloque de subtítulo puede serlo: se
        # envían solo los que tienen contenido y se recolocan en su posición.
        con_texto = [i for i, texto in enumerate(textos) if texto.strip()]
        traducidos = list(textos)

        for lote in _lotes(con_texto, TAMANO_LOTE):
            resultados = self._pedir([textos[i] for i in lote], origen, destino)
            if len(resultados) != len(lote):
                raise ErrorTraduccion(
                    f"DeepL devolvió {len(resultados)} textos para {len(lote)} enviados"
                )
            for i, resultado in zip(lote, resultados, strict=True):
                traducidos[i] = resultado.text
        return traducidos

    def consumo(self) -> Consumo:
        """Caracteres usados y límite del periodo, según DeepL."""
        try:
            caracteres = self._cliente.get_usage().character
        except deepl.DeepLException as exc:
            raise ErrorTraduccion(f"No se pudo consultar el cupo de DeepL: {exc}") from exc
        return Consumo(usados=caracteres.count, limite=caracteres.limit)

    def _pedir(self, textos: list[str], origen: Idioma, destino: Idioma) -> list:
        try:
            resultado = self._cliente.translate_text(
                textos,
                source_lang=origen.value,
                target_lang=destino.value,
                # Respeta los saltos de línea y la puntuación del bloque original.
                preserve_formatting=True,
            )
        except deepl.QuotaExceededException as exc:
            raise CuotaAgotada(f"Cuota de DeepL agotada: {exc}") from exc
        except deepl.AuthorizationException as exc:
            raise ErrorTraduccion(f"DeepL rechaza la clave (DEEPL_API_KEY): {exc}") from exc
        except deepl.DeepLException as exc:
            raise ErrorTraduccion(f"Error de DeepL: {exc}") from exc
        # Con una lista de textos el SDK devuelve una lista de resultados.
        return resultado if isinstance(resultado, list) else [resultado]


def _lotes(indices: list[int], tamano: int) -> Iterator[list[int]]:
    for inicio in range(0, len(indices), tamano):
        yield indices[inicio : inicio + tamano]

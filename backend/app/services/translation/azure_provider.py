"""Proveedor Azure Translator (API REST v3), con `httpx`.

Diferencias con DeepL que explican este módulo:

- **No hay SDK que reintente**: los reintentos ante `429` (demasiado deprisa) y
  errores del servidor se programan aquí, con espera creciente. El plan gratuito F0
  limita el ritmo a 2 M de caracteres por hora en ventana deslizante (~33.000 por
  minuto), y una película ronda los 35.000.
- **No se puede consultar el consumo**: Azure no tiene API para eso. Este proveedor
  no implementa `ConCupo`, y su cupo sale del registro de la app
  (`services/translation/consumo.py`).
- Límites por petición (documentación oficial): 1000 textos y 50.000 caracteres.
"""

import time
from collections.abc import Callable, Iterator

import httpx

from app.models.enums import Idioma
from app.services.translation.base import CuotaAgotada, ErrorTraduccion

URL = "https://api.cognitive.microsofttranslator.com/translate"

# Textos por petición: el ritmo de la barra de progreso de la app (como en DeepL).
TAMANO_LOTE = 50
# Límites de Azure por petición.
MAX_TEXTOS = 1000
MAX_CARACTERES = 50_000

# Reintentos ante 429 o 5xx, esperando 1, 2, 4, 8 y 16 s (o lo que diga Azure en
# `Retry-After`). Tras el último, el trabajo falla con el motivo.
REINTENTOS = 5
TIEMPO_ESPERA_S = 30.0


class TraductorAzure:
    """Implementa `Translator` sobre la API REST de Azure Translator."""

    nombre = "azure"

    def __init__(
        self,
        clave: str,
        region: str | None,
        cliente: httpx.Client | None = None,
        esperar: Callable[[float], None] = time.sleep,
    ) -> None:
        # `cliente` y `esperar` se inyectan en los tests: un transporte falso de
        # httpx y una espera que no duerme.
        self._cliente = cliente or httpx.Client(timeout=TIEMPO_ESPERA_S)
        self._esperar = esperar
        self._cabeceras = {"Ocp-Apim-Subscription-Key": clave}
        # Los recursos regionales exigen la región; los globales, no.
        if region and region.lower() != "global":
            self._cabeceras["Ocp-Apim-Subscription-Region"] = region

    def traducir(self, textos: list[str], origen: Idioma, destino: Idioma) -> list[str]:
        # Como en DeepL: los vacíos no se envían y conservan su sitio.
        con_texto = [i for i, texto in enumerate(textos) if texto.strip()]
        traducidos = list(textos)

        for lote in _lotes(con_texto, textos):
            resultados = self._pedir([textos[i] for i in lote], origen, destino)
            if len(resultados) != len(lote):
                raise ErrorTraduccion(
                    f"Azure devolvió {len(resultados)} textos para {len(lote)} enviados"
                )
            for i, resultado in zip(lote, resultados, strict=True):
                traducidos[i] = resultado
        return traducidos

    def _pedir(self, textos: list[str], origen: Idioma, destino: Idioma) -> list[str]:
        parametros = {
            "api-version": "3.0",
            "from": origen.value.lower(),
            "to": destino.value.lower(),
        }
        cuerpo = [{"Text": texto} for texto in textos]

        for intento in range(REINTENTOS + 1):
            try:
                respuesta = self._cliente.post(
                    URL, params=parametros, headers=self._cabeceras, json=cuerpo
                )
            except httpx.TransportError as exc:
                if intento == REINTENTOS:
                    raise ErrorTraduccion(f"Azure no responde: {exc}") from exc
                self._esperar(2**intento)
                continue

            if respuesta.status_code == 200:
                return [_limpiar(r["translations"][0]["text"]) for r in respuesta.json()]
            if respuesta.status_code in (429, 500, 502, 503, 504) and intento < REINTENTOS:
                self._esperar(_espera(respuesta, intento))
                continue
            _lanzar(respuesta)

        raise ErrorTraduccion("Azure: reintentos agotados")  # no se llega aquí


def _limpiar(texto: str) -> str:
    """Quita los espacios al final de cada línea: Azure deja uno antes de los saltos de
    línea de un diálogo (`- 이름이 뭐였어? \\n- 크리시.`)."""
    return "\n".join(linea.rstrip() for linea in texto.split("\n"))


def _espera(respuesta: httpx.Response, intento: int) -> float:
    """Lo que pida Azure en `Retry-After`, o espera creciente: 1, 2, 4, 8… s."""
    try:
        return float(respuesta.headers["Retry-After"])
    except KeyError, ValueError:
        return float(2**intento)


def _lanzar(respuesta: httpx.Response) -> None:
    """Traduce una respuesta de error de Azure a las excepciones comunes."""
    try:
        detalle = respuesta.json()["error"]["message"]
    except ValueError, KeyError, TypeError:
        detalle = respuesta.text[:200]
    if respuesta.status_code == 401:
        raise ErrorTraduccion(
            f"Azure rechaza la clave (revisa AZURE_TRANSLATOR_KEY y AZURE_TRANSLATOR_REGION): {detalle}"
        )
    if respuesta.status_code == 403:
        # Según la documentación, el 403 suele ser el cupo gratuito agotado.
        raise CuotaAgotada(f"Cupo de Azure agotado: {detalle}")
    if respuesta.status_code == 429:
        # Es el ritmo, no el cupo: el mes no está agotado, solo se fue demasiado deprisa.
        raise ErrorTraduccion(
            f"Azure sigue limitando el ritmo tras {REINTENTOS} reintentos: {detalle}"
        )
    raise ErrorTraduccion(f"Error de Azure ({respuesta.status_code}): {detalle}")


def _lotes(indices: list[int], textos: list[str]) -> Iterator[list[int]]:
    """Agrupa los índices respetando a la vez los tres límites por petición."""
    lote: list[int] = []
    caracteres = 0
    for i in indices:
        largo = len(textos[i])
        lleno = len(lote) >= min(TAMANO_LOTE, MAX_TEXTOS) or caracteres + largo > MAX_CARACTERES
        if lote and lleno:
            yield lote
            lote, caracteres = [], 0
        lote.append(i)
        caracteres += largo
    if lote:
        yield lote

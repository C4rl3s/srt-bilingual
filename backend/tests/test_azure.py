"""Tests del proveedor Azure Translator. Ninguno llama a Azure: `httpx.MockTransport`
hace de servidor."""

import json

import httpx
import pytest

from app.config import settings
from app.models.enums import Idioma
from app.services.translation import registry
from app.services.translation.azure_provider import TAMANO_LOTE, TraductorAzure
from app.services.translation.base import (
    ConCupo,
    CuotaAgotada,
    ErrorTraduccion,
    ProveedorNoDisponible,
    Translator,
)


class ServidorFalso:
    """Imita la API de Azure: apunta las peticiones y responde lo que se le diga."""

    def __init__(self, *respuestas: httpx.Response | None) -> None:
        # `None` en la lista = responder traduciendo; una `Response` = esa respuesta.
        self._respuestas = list(respuestas)
        self.peticiones: list[httpx.Request] = []

    def __call__(self, peticion: httpx.Request) -> httpx.Response:
        self.peticiones.append(peticion)
        forzada = self._respuestas.pop(0) if self._respuestas else None
        if forzada is not None:
            return forzada
        textos = [item["Text"] for item in json.loads(peticion.content)]
        destino = peticion.url.params["to"]
        return httpx.Response(
            200,
            json=[{"translations": [{"text": f"{destino}({t})", "to": destino}]} for t in textos],
        )


def _azure(servidor: ServidorFalso, region: str | None = "westeurope", esperas: list | None = None):
    cliente = httpx.Client(transport=httpx.MockTransport(servidor))
    esperar = esperas.append if esperas is not None else (lambda _s: None)
    return TraductorAzure("clave-de-pega", region, cliente=cliente, esperar=esperar)


def test_cumple_el_protocolo_pero_no_informa_de_su_cupo() -> None:
    """Azure no tiene API de consumo: su cupo sale del registro de la app."""
    traductor = _azure(ServidorFalso())

    assert isinstance(traductor, Translator)
    assert not isinstance(traductor, ConCupo)


def test_traduce_en_orden_con_idiomas_y_cabeceras() -> None:
    servidor = ServidorFalso()

    resultado = _azure(servidor).traducir(["Hola.", "Adiós."], Idioma.ES, Idioma.KO)

    assert resultado == ["ko(Hola.)", "ko(Adiós.)"]
    (peticion,) = servidor.peticiones
    assert (peticion.url.params["from"], peticion.url.params["to"]) == ("es", "ko")
    assert peticion.url.params["api-version"] == "3.0"
    assert peticion.headers["Ocp-Apim-Subscription-Key"] == "clave-de-pega"
    assert peticion.headers["Ocp-Apim-Subscription-Region"] == "westeurope"


def test_quita_los_espacios_al_final_de_cada_linea() -> None:
    """Visto en la prueba real: Azure deja un espacio antes del salto de línea."""
    respuesta = [{"translations": [{"text": "- 이름이 뭐였어? \n- 크리시.", "to": "ko"}]}]
    servidor = ServidorFalso(httpx.Response(200, json=respuesta))

    resultado = _azure(servidor).traducir(
        ["- ¿Cómo era tu nombre?\n- Chrissie."], Idioma.ES, Idioma.KO
    )

    assert resultado == ["- 이름이 뭐였어?\n- 크리시."]


def test_un_recurso_global_no_manda_region() -> None:
    servidor = ServidorFalso()

    _azure(servidor, region="global").traducir(["Hola."], Idioma.ES, Idioma.KO)

    assert "Ocp-Apim-Subscription-Region" not in servidor.peticiones[0].headers


def test_envia_por_lotes() -> None:
    servidor = ServidorFalso()
    textos = [f"frase {i}" for i in range(2 * TAMANO_LOTE + 7)]

    resultado = _azure(servidor).traducir(textos, Idioma.EN, Idioma.KO)

    assert [len(json.loads(p.content)) for p in servidor.peticiones] == [
        TAMANO_LOTE,
        TAMANO_LOTE,
        7,
    ]
    assert resultado[-1] == f"ko(frase {len(textos) - 1})"


def test_respeta_el_limite_de_caracteres_por_peticion() -> None:
    """Azure admite 50.000 caracteres por petición: dos textos de 30.000 van aparte."""
    servidor = ServidorFalso()

    _azure(servidor).traducir(["a" * 30_000, "b" * 30_000], Idioma.ES, Idioma.KO)

    assert len(servidor.peticiones) == 2


def test_los_textos_vacios_no_se_envian_pero_conservan_su_sitio() -> None:
    servidor = ServidorFalso()

    resultado = _azure(servidor).traducir(["Hola.", "", "Adiós."], Idioma.ES, Idioma.KO)

    assert [t["Text"] for t in json.loads(servidor.peticiones[0].content)] == ["Hola.", "Adiós."]
    assert resultado == ["ko(Hola.)", "", "ko(Adiós.)"]


def test_reintenta_ante_429_respetando_retry_after() -> None:
    esperas: list[float] = []
    servidor = ServidorFalso(httpx.Response(429, headers={"Retry-After": "7"}), None)

    resultado = _azure(servidor, esperas=esperas).traducir(["Hola."], Idioma.ES, Idioma.KO)

    assert resultado == ["ko(Hola.)"]
    assert esperas == [7.0]


def test_reintenta_ante_errores_del_servidor_con_espera_creciente() -> None:
    esperas: list[float] = []
    servidor = ServidorFalso(httpx.Response(503), httpx.Response(500), None)

    _azure(servidor, esperas=esperas).traducir(["Hola."], Idioma.ES, Idioma.KO)

    assert esperas == [1.0, 2.0]


def test_un_429_que_no_cede_es_error_de_ritmo_no_de_cupo() -> None:
    servidor = ServidorFalso(*[httpx.Response(429) for _ in range(10)])

    with pytest.raises(ErrorTraduccion, match="ritmo") as fallo:
        _azure(servidor).traducir(["Hola."], Idioma.ES, Idioma.KO)
    assert not isinstance(fallo.value, CuotaAgotada)


def test_el_403_es_cupo_agotado() -> None:
    servidor = ServidorFalso(
        httpx.Response(403, json={"error": {"code": 403001, "message": "Out of call volume quota"}})
    )

    with pytest.raises(CuotaAgotada, match="Out of call volume quota"):
        _azure(servidor).traducir(["Hola."], Idioma.ES, Idioma.KO)


def test_una_clave_rechazada_explica_que_revisar() -> None:
    servidor = ServidorFalso(httpx.Response(401, json={"error": {"message": "Access denied"}}))

    with pytest.raises(ErrorTraduccion, match="AZURE_TRANSLATOR_KEY"):
        _azure(servidor).traducir(["Hola."], Idioma.ES, Idioma.KO)


def test_no_se_fia_de_una_respuesta_con_menos_textos() -> None:
    servidor = ServidorFalso(httpx.Response(200, json=[{"translations": [{"text": "x"}]}]))

    with pytest.raises(ErrorTraduccion, match="devolvió 1 textos para 2"):
        _azure(servidor).traducir(["a", "b"], Idioma.ES, Idioma.KO)


def test_el_registro_crea_azure_solo_con_clave(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ProveedorNoDisponible, match="AZURE_TRANSLATOR_KEY"):
        registry.obtener_traductor("azure")

    monkeypatch.setattr(settings, "azure_translator_key", "clave-de-pega")
    monkeypatch.setattr(settings, "azure_translator_region", "westeurope")

    assert registry.obtener_traductor("azure").nombre == "azure"
    assert registry.limite_configurado("azure") == settings.azure_translator_limite_mensual

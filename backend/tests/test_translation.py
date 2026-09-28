"""Tests de la capa de traducción. Ninguno llama a DeepL de verdad."""

import deepl
import pytest

from app.config import settings
from app.models.enums import Idioma
from app.services.translation import registry
from app.services.translation.base import (
    CuotaAgotada,
    ErrorTraduccion,
    ProveedorNoDisponible,
    Translator,
)
from app.services.translation.deepl_provider import TAMANO_LOTE, TraductorDeepL
from tests.conftest import TraductorFalso


class _Resultado:
    """Imita `deepl.TextResult`: solo se usa su `text`."""

    def __init__(self, text: str) -> None:
        self.text = text


class ClienteDeepLFalso:
    """Imita `deepl.Translator.translate_text` y apunta cada petición."""

    def __init__(self, error: Exception | None = None, recortar: bool = False) -> None:
        self.peticiones: list[dict] = []
        self._error = error
        self._recortar = recortar

    def translate_text(self, textos, **opciones):
        self.peticiones.append({"textos": list(textos), **opciones})
        if self._error is not None:
            raise self._error
        resultados = [_Resultado(f"한국어({texto})") for texto in textos]
        return resultados[:-1] if self._recortar else resultados


def _deepl(cliente: ClienteDeepLFalso) -> TraductorDeepL:
    return TraductorDeepL("clave-de-pega:fx", cliente=cliente)


def test_los_proveedores_cumplen_el_protocolo() -> None:
    assert isinstance(_deepl(ClienteDeepLFalso()), Translator)
    assert isinstance(TraductorFalso(), Translator)


def test_traduce_en_orden_y_con_los_idiomas_pedidos() -> None:
    cliente = ClienteDeepLFalso()

    resultado = _deepl(cliente).traducir(["Hola.", "Adiós."], Idioma.ES, Idioma.KO)

    assert resultado == ["한국어(Hola.)", "한국어(Adiós.)"]
    (peticion,) = cliente.peticiones
    assert (peticion["source_lang"], peticion["target_lang"]) == ("ES", "KO")


def test_envia_por_lotes() -> None:
    """Una película de 1500 bloques no puede ser 1500 peticiones."""
    cliente = ClienteDeepLFalso()
    textos = [f"frase {i}" for i in range(2 * TAMANO_LOTE + 7)]

    resultado = _deepl(cliente).traducir(textos, Idioma.EN, Idioma.KO)

    assert [len(p["textos"]) for p in cliente.peticiones] == [TAMANO_LOTE, TAMANO_LOTE, 7]
    assert resultado[-1] == f"한국어(frase {len(textos) - 1})"


def test_los_textos_vacios_no_se_envian_pero_conservan_su_sitio() -> None:
    cliente = ClienteDeepLFalso()

    resultado = _deepl(cliente).traducir(["Hola.", "", "  ", "Adiós."], Idioma.ES, Idioma.KO)

    assert cliente.peticiones[0]["textos"] == ["Hola.", "Adiós."]
    assert resultado == ["한국어(Hola.)", "", "  ", "한국어(Adiós.)"]


def test_no_se_fia_de_un_proveedor_que_devuelve_menos_textos() -> None:
    with pytest.raises(ErrorTraduccion, match="devolvió 1 textos para 2"):
        _deepl(ClienteDeepLFalso(recortar=True)).traducir(["a", "b"], Idioma.ES, Idioma.KO)


def test_la_cuota_agotada_se_distingue() -> None:
    cliente = ClienteDeepLFalso(error=deepl.QuotaExceededException("límite"))

    with pytest.raises(CuotaAgotada):
        _deepl(cliente).traducir(["Hola."], Idioma.ES, Idioma.KO)


def test_una_clave_rechazada_explica_que_revisar() -> None:
    cliente = ClienteDeepLFalso(error=deepl.AuthorizationException("403"))

    with pytest.raises(ErrorTraduccion, match="DEEPL_API_KEY"):
        _deepl(cliente).traducir(["Hola."], Idioma.ES, Idioma.KO)


def test_el_registro_da_el_proveedor_configurado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "deepl_api_key", "clave-de-pega:fx")
    monkeypatch.setattr(settings, "translation_provider", "DeepL")  # sin distinguir mayúsculas

    traductor = registry.obtener_traductor()

    assert traductor.nombre == "deepl"


def test_el_registro_avisa_si_falta_la_clave(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "deepl_api_key", None)

    with pytest.raises(ProveedorNoDisponible, match="DEEPL_API_KEY"):
        registry.obtener_traductor("deepl")


def test_el_registro_rechaza_un_proveedor_desconocido() -> None:
    with pytest.raises(ProveedorNoDisponible, match="desconocido"):
        registry.obtener_traductor("babelfish")

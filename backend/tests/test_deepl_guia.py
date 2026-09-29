"""Tests de DeepL con la guía de la serie: glosario, instrucciones y diálogos.

Ninguno llama a DeepL: el cliente falso imita `translate_text` y la gestión de
glosarios del SDK y apunta cada llamada.
"""

from pathlib import Path

import deepl
import pytest

from app.models.enums import Idioma
from app.services.translation.azure_provider import TraductorAzure
from app.services.translation.base import ErrorTraduccion, Translator
from app.services.translation.deepl_provider import PREFIJO_GLOSARIO, TraductorDeepL
from app.services.translation.guia import Guia
from tests.test_translation import ClienteDeepLFalso


class _Glosario:
    """Imita `deepl.GlossaryInfo`: solo se usan su nombre y su id."""

    def __init__(self, name: str, glossary_id: str) -> None:
        self.name = name
        self.glossary_id = glossary_id


class ClienteConGlosarios(ClienteDeepLFalso):
    """Añade al cliente falso la gestión de glosarios de la cuenta."""

    def __init__(self, existentes: list[_Glosario] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.cuenta: list[_Glosario] = list(existentes or [])
        self.creados: list[dict] = []
        self.borrados: list[str] = []
        self.listados = 0
        self.error_al_crear: Exception | None = None

    def list_glossaries(self):
        self.listados += 1
        return list(self.cuenta)

    def create_glossary(self, name, source_lang, target_lang, entries):
        if self.error_al_crear is not None:
            raise self.error_al_crear
        nuevo = _Glosario(name, f"id-{len(self.creados)}")
        self.creados.append(
            {"name": name, "source": source_lang, "target": target_lang, "entries": dict(entries)}
        )
        self.cuenta.append(nuevo)
        return nuevo

    def delete_glossary(self, glosario):
        self.borrados.append(glosario.name)
        self.cuenta = [g for g in self.cuenta if g is not glosario]


def _guia(
    glosario: dict[str, str] | None = None,
    instrucciones: tuple[str, ...] = (),
    ruta: str = r"Z:\Anime\Shingeki\srt-bilingual.toml",
) -> Guia:
    return Guia(ruta=Path(ruta), glosario=glosario or {}, instrucciones=instrucciones)


GUIA = _guia({"Marley": "마레", "titán acorazado": "갑옷 거인"}, ("Usa 반말 entre amigos.",))


def _deepl(cliente: ClienteDeepLFalso) -> TraductorDeepL:
    return TraductorDeepL("clave-de-pega:fx", cliente=cliente)


def test_los_proveedores_declaran_si_admiten_la_guia() -> None:
    assert _deepl(ClienteConGlosarios()).admite_guia
    assert not TraductorAzure("clave", None).admite_guia
    assert isinstance(_deepl(ClienteConGlosarios()), Translator)


def test_sin_guia_la_peticion_no_cambia() -> None:
    cliente = ClienteConGlosarios()

    _deepl(cliente).traducir(["Hola."], Idioma.ES, Idioma.KO)

    (peticion,) = cliente.peticiones
    assert "glossary" not in peticion
    assert "extra_body_parameters" not in peticion
    assert cliente.listados == 0  # ni siquiera mira los glosarios de la cuenta


def test_crea_el_glosario_y_lo_usa_en_cada_lote() -> None:
    cliente = ClienteConGlosarios()
    textos = [f"frase {i}" for i in range(120)]  # tres lotes

    _deepl(cliente).traducir(textos, Idioma.ES, Idioma.KO, GUIA)

    (creado,) = cliente.creados
    assert creado["name"].startswith(f"{PREFIJO_GLOSARIO}:")
    assert creado["name"].endswith(f":{GUIA.huella}:ES-KO")
    assert (creado["source"], creado["target"]) == ("ES", "KO")
    assert creado["entries"] == GUIA.glosario
    assert len(cliente.peticiones) == 3
    assert all(p["glossary"].name == creado["name"] for p in cliente.peticiones)


def test_reutiliza_el_glosario_en_el_mismo_proceso() -> None:
    cliente = ClienteConGlosarios()
    deepl_ = _deepl(cliente)

    deepl_.traducir(["Uno."], Idioma.ES, Idioma.KO, GUIA)
    deepl_.traducir(["Dos."], Idioma.ES, Idioma.KO, GUIA)

    assert len(cliente.creados) == 1
    assert cliente.listados == 1


def test_reutiliza_el_glosario_ya_creado_en_la_cuenta() -> None:
    # Otro proceso (un reinicio del backend) lo creó antes: no se duplica.
    primero = ClienteConGlosarios()
    _deepl(primero).traducir(["Uno."], Idioma.ES, Idioma.KO, GUIA)
    segundo = ClienteConGlosarios(existentes=primero.cuenta)

    _deepl(segundo).traducir(["Dos."], Idioma.ES, Idioma.KO, GUIA)

    assert segundo.creados == []
    assert segundo.peticiones[0]["glossary"] is primero.cuenta[0]


def test_si_la_guia_cambia_sustituye_solo_su_version_anterior() -> None:
    otra_guia = _guia({"Konoha": "나뭇잎"}, ruta=r"Z:\Anime\Naruto\srt-bilingual.toml")
    ajeno = _Glosario("mi glosario personal", "id-ajeno")
    cliente = ClienteConGlosarios(existentes=[ajeno])
    _deepl(cliente).traducir(["Uno."], Idioma.ES, Idioma.KO, GUIA)
    _deepl(cliente).traducir(["Uno."], Idioma.ES, Idioma.KO, otra_guia)
    viejo, de_otra = (c["name"] for c in cliente.creados)

    cambiada = _guia({**GUIA.glosario, "Paradis": "파라디"}, GUIA.instrucciones)
    _deepl(cliente).traducir(["Dos."], Idioma.ES, Idioma.KO, cambiada)

    assert cliente.borrados == [viejo]
    nombres = {g.name for g in cliente.cuenta}
    assert de_otra in nombres  # la guía de otra serie sigue
    assert "mi glosario personal" in nombres  # lo que no es de la app no se toca
    assert cliente.creados[-1]["entries"]["Paradis"] == "파라디"


def test_la_misma_guia_con_otra_grafia_de_ruta_es_la_misma() -> None:
    cliente = ClienteConGlosarios()
    _deepl(cliente).traducir(["Uno."], Idioma.ES, Idioma.KO, GUIA)
    minusculas = _guia(GUIA.glosario, GUIA.instrucciones, ruta=str(GUIA.ruta).lower())

    _deepl(cliente).traducir(["Dos."], Idioma.ES, Idioma.KO, minusculas)

    assert len(cliente.creados) == 1


def test_con_origen_ingles_no_hay_glosario_pero_si_instrucciones() -> None:
    cliente = ClienteConGlosarios()

    _deepl(cliente).traducir(["Hello."], Idioma.EN, Idioma.KO, GUIA)

    (peticion,) = cliente.peticiones
    assert "glossary" not in peticion
    assert peticion["extra_body_parameters"] == {"custom_instructions": list(GUIA.instrucciones)}
    assert cliente.creados == []


def test_las_instrucciones_van_en_custom_instructions() -> None:
    cliente = ClienteConGlosarios()
    solo_instrucciones = _guia(instrucciones=("Uno.", "Dos."))

    _deepl(cliente).traducir(["Hola."], Idioma.ES, Idioma.KO, solo_instrucciones)

    (peticion,) = cliente.peticiones
    assert peticion["extra_body_parameters"] == {"custom_instructions": ["Uno.", "Dos."]}
    assert "glossary" not in peticion


def test_con_instrucciones_cada_linea_de_un_dialogo_va_sola() -> None:
    cliente = ClienteConGlosarios()
    dialogo = "-El poder de los titanes.\n-En efecto."

    resultado = _deepl(cliente).traducir(["Hola.", dialogo, ""], Idioma.ES, Idioma.KO, GUIA)

    assert cliente.peticiones[0]["textos"] == [
        "Hola.",
        "-El poder de los titanes.",
        "-En efecto.",
    ]
    assert resultado == [
        "한국어(Hola.)",
        "한국어(-El poder de los titanes.)\n한국어(-En efecto.)",
        "",
    ]


def test_sin_instrucciones_el_dialogo_va_entero() -> None:
    cliente = ClienteConGlosarios()
    dialogo = "-El poder de los titanes.\n-En efecto."

    _deepl(cliente).traducir([dialogo], Idioma.ES, Idioma.KO, _guia({"Marley": "마레"}))

    assert cliente.peticiones[0]["textos"] == [dialogo]


def test_un_fallo_al_crear_el_glosario_es_un_error_de_traduccion() -> None:
    cliente = ClienteConGlosarios()
    cliente.error_al_crear = deepl.DeepLException("demasiados glosarios")

    with pytest.raises(ErrorTraduccion, match="glosario"):
        _deepl(cliente).traducir(["Hola."], Idioma.ES, Idioma.KO, GUIA)
    assert cliente.peticiones == []  # no se traduce sin él


def test_azure_recibe_la_guia_y_la_ignora() -> None:
    enviados: list = []

    class Cliente:
        def post(self, url, params, headers, json):
            enviados.append(json)

            class Respuesta:
                status_code = 200

                @staticmethod
                def json():
                    return [{"translations": [{"text": "안녕"}]}]

            return Respuesta()

    resultado = TraductorAzure("clave", None, cliente=Cliente()).traducir(
        ["Hola."], Idioma.ES, Idioma.KO, GUIA
    )

    assert resultado == ["안녕"]
    assert enviados == [[{"Text": "Hola."}]]

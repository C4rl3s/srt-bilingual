"""Tests de la selección del subtítulo de origen, con los casos reales del sondeo."""

from itertools import count

from app.models.enums import EstadoSubtitulo, Idioma
from app.models.subtitle_file import ArchivoSubtitulo
from app.services.subtitles.seleccion import MotivoDescarte, seleccionar

_ids = count(1)


def _sub(
    nombre: str,
    idioma: Idioma,
    bloques: int,
    *,
    forzado: bool = False,
    sdh: bool = False,
    estado: EstadoSubtitulo = EstadoSubtitulo.PENDING,
) -> ArchivoSubtitulo:
    """Fila en memoria, sin base de datos: la selección solo lee sus atributos."""
    return ArchivoSubtitulo(
        id=next(_ids),
        ruta=f"/pelis/obra/{nombre}",
        nombre=nombre,
        idioma_origen=idioma,
        num_bloques=bloques,
        es_forzado=forzado,
        es_sdh=sdh,
        estado=estado,
    )


def _motivo(seleccion, sub: ArchivoSubtitulo) -> MotivoDescarte | None:
    return next(c.descarte for c in seleccion.candidatos if c.subtitulo is sub)


def test_mercy_elige_el_espanol_completo_y_descarta_los_forzados() -> None:
    latino = _sub("Latin American.spa.srt", Idioma.ES, 2015)
    junto_al_video = _sub("Mercy.2026.spa.srt", Idioma.ES, 2009)
    europeo = _sub("European.spa.srt", Idioma.ES, 1779)
    forzado = _sub("Latin American (Forced).spa.srt", Idioma.ES, 61, forzado=True)

    seleccion = seleccionar([forzado, europeo, junto_al_video, latino])

    assert seleccion.origen is latino  # el más completo
    assert _motivo(seleccion, forzado) is MotivoDescarte.FORZADO


def test_el_espanol_gana_al_ingles_aunque_tenga_menos_bloques() -> None:
    ingles = _sub("Pelicula.eng.srt", Idioma.EN, 2069)
    espanol = _sub("Pelicula.spa.srt", Idioma.ES, 1502)

    assert seleccionar([ingles, espanol]).origen is espanol


def test_un_forzado_encubierto_se_descarta_por_su_tamano() -> None:
    """*Bugonia*: un `.srt` sin idioma en el nombre con 25 bloques frente a 2069."""
    completo = _sub("Bugonia.eng.srt", Idioma.EN, 2069)
    encubierto = _sub("Bugonia.srt", Idioma.EN, 25)

    seleccion = seleccionar([encubierto, completo])

    assert seleccion.origen is completo
    assert _motivo(seleccion, encubierto) is MotivoDescarte.POCOS_BLOQUES


def test_un_forzado_encubierto_solo_no_es_origen() -> None:
    """*Thunderbolts*: su único `.srt` tiene 33 bloques. Mejor no elegible que un
    bilingüe con cuatro carteles."""
    seleccion = seleccionar([_sub("Thunderbolts.srt", Idioma.EN, 33)])

    assert not seleccion.elegible


def test_el_sdh_no_infla_la_referencia() -> None:
    """*Predator: Killer of Killers*: el SDH tiene 994 bloques y el resto ~430. Si
    fuera la referencia, el inglés completo (367) pasaría por forzado."""
    sdh = _sub("SDH.eng.HI.srt", Idioma.EN, 994, sdh=True)
    ingles = _sub("Pelicula.eng.srt", Idioma.EN, 367)
    otro = _sub("por.srt", Idioma.PT, 432)

    seleccion = seleccionar([sdh, ingles, otro])

    assert seleccion.origen is ingles  # y no el SDH, que queda como último recurso
    assert _motivo(seleccion, ingles) is None


def test_el_sdh_sirve_si_no_hay_otro() -> None:
    sdh = _sub("SDH.eng.HI.srt", Idioma.EN, 900, sdh=True)

    assert seleccionar([sdh]).origen is sdh


def test_sin_espanol_ni_ingles_no_es_elegible() -> None:
    danes = _sub("dan.srt", Idioma.UNKNOWN, 1080)
    frances = _sub("fre.srt", Idioma.FR, 1000)

    seleccion = seleccionar([danes, frances])

    assert not seleccion.elegible
    assert {c.descarte for c in seleccion.candidatos} == {MotivoDescarte.IDIOMA}


def test_localiza_el_coreano_para_fusionar() -> None:
    """*Jaws*: español + coreano → bilingüe por fusión, sin traducir."""
    espanol = _sub("Jaws.spa.srt", Idioma.ES, 1253)
    coreano = _sub("Jaws.ko.srt", Idioma.KO, 1188)

    seleccion = seleccionar([espanol, coreano])

    assert seleccion.origen is espanol
    assert seleccion.coreano is coreano


def test_solo_coreano_no_es_elegible() -> None:
    """*The Sixth Sense*: hay coreano pero falta el origen ES/EN."""
    seleccion = seleccionar([_sub("Sixth.Sense.ko.srt", Idioma.KO, 887)])

    assert not seleccion.elegible
    assert seleccion.coreano is not None


def test_un_fichero_ilegible_no_impide_elegir_otro() -> None:
    roto = _sub("Roto.spa.srt", Idioma.ES, 0, estado=EstadoSubtitulo.ERROR)
    bueno = _sub("Bueno.eng.srt", Idioma.EN, 1200)

    seleccion = seleccionar([roto, bueno])

    assert seleccion.origen is bueno
    assert _motivo(seleccion, roto) is MotivoDescarte.ERROR


def test_el_override_manual_gana_a_la_heuristica() -> None:
    espanol = _sub("Pelicula.spa.srt", Idioma.ES, 1500)
    ingles = _sub("Pelicula.eng.srt", Idioma.EN, 1400)

    assert seleccionar([espanol, ingles], origen_preferido_id=ingles.id).origen is ingles


def test_el_override_puede_rescatar_un_subtitulo_corto() -> None:
    """El usuario sabe si una película casi no tiene diálogo."""
    corto = _sub("Muda.spa.srt", Idioma.ES, 60)

    assert seleccionar([corto], origen_preferido_id=corto.id).origen is corto


def test_el_override_no_acepta_un_idioma_que_no_sirve_de_origen() -> None:
    espanol = _sub("Pelicula.spa.srt", Idioma.ES, 1500)
    frances = _sub("Pelicula.fre.srt", Idioma.FR, 1500)

    assert seleccionar([espanol, frances], origen_preferido_id=frances.id).origen is espanol

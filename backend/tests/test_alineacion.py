"""Tests de la alineación de un coreano existente con el origen (modo fusión)."""

import random
from datetime import timedelta

import pytest

from app.services.subtitles.alineacion import MetodoAlineacion, alinear
from app.services.subtitles.modelo import Bloque


def _bloques(tramos: list[tuple[float, float, str]]) -> list[Bloque]:
    return [
        Bloque(
            indice=i + 1,
            inicio=timedelta(seconds=inicio),
            fin=timedelta(seconds=fin),
            contenido=texto,
        )
        for i, (inicio, fin, texto) in enumerate(tramos)
    ]


def _dialogo(n: int = 60, semilla: int = 7) -> list[tuple[float, float, str]]:
    """Frases de duración y separación irregulares, como en una película real (con
    un ritmo regular, cualquier desplazamiento de un periodo cuadraría igual)."""
    azar = random.Random(semilla)
    tramos, t = [], 5.0
    for i in range(n):
        duracion = azar.uniform(1.2, 4.0)
        tramos.append((t, t + duracion, f"frase {i}"))
        t += duracion + azar.uniform(0.3, 6.0)
    return tramos


def _coreano(tramos, desplazamiento: float = 0.0, factor: float = 1.0):
    return [
        (i * factor + desplazamiento, f * factor + desplazamiento, f"문장 {n}")
        for n, (i, f, _) in enumerate(tramos)
    ]


def test_mismo_numero_de_bloques_y_sincronizados_va_uno_a_uno() -> None:
    dialogo = _dialogo()

    resultado = alinear(_bloques(dialogo), _bloques(_coreano(dialogo)))

    assert resultado.metodo is MetodoAlineacion.UNO_A_UNO
    assert resultado.textos == [f"문장 {n}" for n in range(len(dialogo))]
    assert resultado.calidad == 1.0
    assert resultado.aceptable


def test_corrige_un_desfase_constante() -> None:
    """Mismo número de bloques pero 2,5 s tarde: se detecta y se empareja 1:1."""
    dialogo = _dialogo()

    resultado = alinear(_bloques(dialogo), _bloques(_coreano(dialogo, desplazamiento=2.5)))

    assert resultado.desplazamiento.total_seconds() == pytest.approx(-2.5, abs=0.05)
    assert resultado.metodo is MetodoAlineacion.UNO_A_UNO
    assert resultado.textos[10] == "문장 10"


def test_corrige_el_cambio_de_velocidad_entre_versiones() -> None:
    """Coreano sacado de una versión a 25 fps; el origen, de una a 23,976."""
    dialogo = _dialogo()

    resultado = alinear(_bloques(dialogo), _bloques(_coreano(dialogo, factor=23.976 / 25)))

    assert resultado.factor == pytest.approx(25 / 23.976)
    assert resultado.textos[-1] == f"문장 {len(dialogo) - 1}"
    assert resultado.aceptable


def test_segmentacion_distinta() -> None:
    """El caso *Jaws*: el coreano junta en un bloque lo que el origen parte en dos, y
    parte en dos lo que el origen dice en uno."""
    origen = _bloques(
        [
            (10.0, 12.0, "¿Cómo te llamas?"),
            (20.0, 21.5, "Espera."),
            (22.0, 24.0, "Más despacio."),
            (30.0, 34.0, "No estoy borracho. ¡Espera!"),
        ]
    )
    coreano = _bloques(
        [
            (10.0, 12.0, "이름이 뭐야?"),
            (20.2, 23.8, "천천히 가"),  # cubre "Espera." y "Más despacio."
            (30.0, 32.0, "나 안 취했어!"),  # "No estoy borracho…" partido en dos
            (32.0, 34.0, "좀 천천히 가!"),
        ]
    )

    resultado = alinear(origen, coreano)

    assert resultado.metodo is MetodoAlineacion.SOLAPE
    assert resultado.textos == [
        "이름이 뭐야?",
        "",  # el coreano va con el bloque con el que más comparte
        "천천히 가",
        "나 안 취했어!\n좀 천천히 가!",  # dos bloques coreanos, unidos en orden
    ]


def test_hay_un_texto_por_bloque_de_origen() -> None:
    """La invariante que permite al generador recomponer el bilingüe."""
    dialogo = _dialogo()
    coreano = _coreano(dialogo)[::2]  # al coreano le faltan la mitad de las frases

    resultado = alinear(_bloques(dialogo), _bloques(coreano))

    assert len(resultado.textos) == len(dialogo)


def test_un_bloque_coreano_lejos_de_todo_queda_descolocado() -> None:
    origen = _bloques([(10.0, 12.0, "Hola."), (20.0, 22.0, "Adiós.")])
    coreano = _bloques([(10.0, 12.0, "안녕."), (20.0, 22.0, "잘 가."), (50.0, 52.0, "♪ 노래 ♪")])

    resultado = alinear(origen, coreano)

    assert resultado.textos == ["안녕.", "잘 가."]
    assert resultado.descolocados == 1


def test_un_coreano_de_otra_version_no_es_aceptable() -> None:
    """Dos diálogos sin relación: la mejor transformación solapa poco."""
    resultado = alinear(_bloques(_dialogo(semilla=1)), _bloques(_coreano(_dialogo(semilla=2))))

    assert not resultado.aceptable

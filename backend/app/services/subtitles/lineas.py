"""Líneas de un bloque: cómo se envían a traducir y cómo vuelve el coreano.

En un `.srt` una frase larga se parte en dos líneas para que quepa en pantalla
(«Concluyen ya los festejos por el proyecto / del eje orbital de Sapientia»). Si se
envía así, el proveedor traduce **cada línea como una frase suelta**, y salen dos
mitades que no casan, a veces con el sentido invertido: era la causa principal de
los errores de Azure en la prueba de calidad de la Fase 5 (hito 6, en
`docs/bitacora-fase5.md`).

Por eso, antes de traducir, las líneas de un bloque se **unen** en una sola frase, y
el coreano que vuelve se **reparte** otra vez en dos líneas si es largo.

La excepción son los **diálogos**: un bloque con una línea por personaje, cada una
con su guion («- ¡Vamos! / - ¿Qué? Espera…»). Unirlos juntaría dos voces en una sola
frase; se envían como estaban.
"""

import re

# Guion de diálogo al principio de la línea (con o sin etiqueta de estilo delante).
_GUION = re.compile(r"^\s*(?:<[^>]+>)*\s*[-–—]")

# A partir de estos caracteres el coreano se reparte en dos líneas. El coreano es más
# denso que el español: una línea de subtítulo de Netflix ronda los 11 caracteres de
# media y rara vez pasa de 20 en una línea.
LARGO_PARA_PARTIR = 18


def es_dialogo(texto: str) -> bool:
    """Si el bloque es un diálogo: varias líneas y todas empiezan con guion."""
    lineas = [linea for linea in texto.splitlines() if linea.strip()]
    return len(lineas) > 1 and all(_GUION.match(linea) for linea in lineas)


def para_traducir(texto: str) -> str:
    """El texto del bloque tal como se envía al proveedor: una frase por bloque."""
    if es_dialogo(texto):
        return texto
    return " ".join(linea.strip() for linea in texto.splitlines() if linea.strip())


def recolocar(original: str, traducido: str) -> str:
    """El coreano en líneas como el original: si este venía partido (y no es un
    diálogo, que ya vuelve con sus líneas) y el coreano es largo, en dos líneas."""
    traducido = traducido.strip()
    lineas_original = [linea for linea in original.splitlines() if linea.strip()]
    if len(lineas_original) < 2 or es_dialogo(original) or len(traducido) < LARGO_PARA_PARTIR:
        return traducido
    return partir_en_dos(traducido)


def partir_en_dos(texto: str) -> str:
    """Parte el texto en dos líneas por el espacio más cercano al centro.

    Sin espacios (o con uno solo al borde) se deja entero: una línea larga se lee
    mejor que una palabra suelta en la segunda.
    """
    centro = len(texto) / 2
    espacios = [i for i, caracter in enumerate(texto) if caracter == " "]
    if not espacios:
        return texto
    corte = min(espacios, key=lambda i: abs(i - centro))
    primera, segunda = texto[:corte].rstrip(), texto[corte + 1 :].lstrip()
    if not primera or not segunda:
        return texto
    return f"{primera}\n{segunda}"

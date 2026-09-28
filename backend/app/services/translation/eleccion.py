"""Elección automática del proveedor de cada traducción según su cupo libre.

Regla (Fase 4): el primero, en el orden de preferencia de `TRANSLATION_PROVIDERS`,
que tenga cupo libre para toda la película, con un margen. Si ninguno llega, no se
traduce: mejor avisar antes que agotar un cupo a mitad de película.
"""

from collections import defaultdict

from app.services.translation.consumo import EstadoCupo

# Cada proveedor cuenta los caracteres a su manera (saltos de línea, espacios…):
# se pide un 5 % de holgura sobre lo previsto.
MARGEN = 1.05


class Asignador:
    """Reparte las traducciones de una petición entre los proveedores.

    Lleva la cuenta de lo que va asignando: si se piden 20 películas, las reservas
    de las primeras cuentan para las siguientes, y no se mandan todas al mismo
    proveedor aunque cada una quepa por separado.
    """

    def __init__(self, estados: list[EstadoCupo]) -> None:
        self._estados = estados
        self._asignado: dict[str, int] = defaultdict(int)

    def asignar(self, caracteres: int, solo: str | None = None) -> str | None:
        """El proveedor para una traducción de `caracteres`, o `None` si no cabe.

        Con `solo`, el usuario ha elegido proveedor para esa obra: se le aplica la misma
        regla (disponible y con cupo), pero sin probar con los demás.
        """
        necesarios = caracteres * MARGEN
        for estado in self._candidatos(solo):
            if not estado.disponible:
                continue
            libre = self._libre(estado)
            # Límite desconocido (la API de DeepL no responde): se confía en él. Si
            # de verdad se agota, el trabajo fallará con `CuotaAgotada` y el
            # reintento pasará al siguiente proveedor.
            if libre is None or libre >= necesarios:
                self._asignado[estado.proveedor] += caracteres
                return estado.proveedor
        return None

    def motivo(self, caracteres: int, solo: str | None = None) -> str:
        """Por qué no cabe `caracteres` en ningún proveedor (o en el pedido), para el
        usuario."""
        estados = self._candidatos(solo)
        if solo is not None and not estados:
            return f"{solo} no es un proveedor configurado (ver TRANSLATION_PROVIDERS)"
        detalles = []
        for estado in estados:
            if not estado.disponible:
                detalles.append(f"{estado.proveedor}: {estado.motivo}")
            else:
                detalles.append(f"{estado.proveedor}: {_miles(self._libre(estado) or 0)} libres")
        lista = "; ".join(detalles) if detalles else "no hay proveedores configurados"
        return f"Sin cupo suficiente para {_miles(caracteres)} caracteres ({lista})"

    def _candidatos(self, solo: str | None) -> list[EstadoCupo]:
        if solo is None:
            return self._estados
        return [estado for estado in self._estados if estado.proveedor == solo]

    def _libre(self, estado: EstadoCupo) -> int | None:
        if estado.libre is None:
            return None
        return estado.libre - self._asignado[estado.proveedor]


def _miles(numero: int) -> str:
    """64751 → «64.751», como en la interfaz."""
    return f"{numero:,}".replace(",", ".")

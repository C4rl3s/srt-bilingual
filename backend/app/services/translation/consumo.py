"""Consumo de cupo por proveedor: cuánto lleva gastado, cuánto tiene reservado y
cuánto le queda.

Dos fuentes, por orden de preferencia:

- **La API del proveedor** (`ConCupo`, p. ej. DeepL): la cifra real, incluido lo
  gastado con esa clave fuera de la app.
- **El registro de la app** (Azure, que no deja consultarlo): la suma de los
  caracteres enviados en `translation_job` desde el día 1 del mes, contra un límite
  configurado. No ve lo gastado fuera de la app.

Además, lo que los trabajos en cola o en curso aún no han enviado queda
**reservado**: sin esto, dos peticiones seguidas podrían contar con el mismo cupo.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import EstadoTrabajo
from app.models.translation_job import TrabajoTraduccion
from app.services.translation.base import ConCupo, ErrorTraduccion, Translator

type FabricaTraductor = Callable[[str | None], Translator]
type LimiteConfigurado = Callable[[str], int | None]


class FuenteCupo(str, Enum):
    API = "API"  # lo dice el proveedor
    REGISTRO = "REGISTRO"  # suma de lo enviado por la app este mes


@dataclass(frozen=True, slots=True)
class EstadoCupo:
    """El cupo de un proveedor en este momento."""

    proveedor: str
    # Si se puede usar ahora (tiene clave, la app lo conoce…). Si no, el motivo.
    disponible: bool
    motivo: str | None
    fuente: FuenteCupo
    usados: int
    reservados: int
    limite: int | None  # None: sin límite conocido

    @property
    def libre(self) -> int | None:
        """Lo que se puede gastar aún, o `None` si el límite no se conoce."""
        if self.limite is None:
            return None
        return max(0, self.limite - self.usados - self.reservados)


def estados(
    db: Session,
    nombres: list[str],
    fabrica_traductor: FabricaTraductor,
    limite_configurado: LimiteConfigurado,
    ahora: datetime | None = None,
) -> list[EstadoCupo]:
    """El cupo de cada proveedor de `nombres`, en ese mismo orden."""
    return [estado(db, nombre, fabrica_traductor, limite_configurado, ahora) for nombre in nombres]


def estado(
    db: Session,
    nombre: str,
    fabrica_traductor: FabricaTraductor,
    limite_configurado: LimiteConfigurado,
    ahora: datetime | None = None,
) -> EstadoCupo:
    reservados = _reservados(db, nombre)
    try:
        traductor = fabrica_traductor(nombre)
    except ErrorTraduccion as exc:
        # Sin clave o desconocido: se informa igual, para que la interfaz diga por qué.
        return EstadoCupo(nombre, False, str(exc), FuenteCupo.REGISTRO, 0, reservados, None)

    if isinstance(traductor, ConCupo):
        try:
            consumo = traductor.consumo()
            return EstadoCupo(
                nombre, True, None, FuenteCupo.API, consumo.usados, reservados, consumo.limite
            )
        except ErrorTraduccion:
            pass  # la API no responde: se cae al registro propio, sin límite conocido

    usados = _usados_este_mes(db, nombre, ahora or datetime.now(UTC))
    return EstadoCupo(
        nombre, True, None, FuenteCupo.REGISTRO, usados, reservados, limite_configurado(nombre)
    )


def _reservados(db: Session, proveedor: str) -> int:
    """Lo que sus trabajos en cola o en curso aún no han enviado."""
    pendiente = func.max(
        TrabajoTraduccion.caracteres_previstos - TrabajoTraduccion.num_caracteres, 0
    )
    total = db.scalar(
        select(func.coalesce(func.sum(pendiente), 0)).where(
            TrabajoTraduccion.proveedor == proveedor,
            TrabajoTraduccion.estado.in_([EstadoTrabajo.QUEUED, EstadoTrabajo.RUNNING]),
        )
    )
    return int(total or 0)


def _usados_este_mes(db: Session, proveedor: str, ahora: datetime) -> int:
    """Caracteres enviados por la app a `proveedor` desde el día 1 del mes (UTC).

    Cuentan también los de trabajos fallidos: el proveedor ya los cobró.
    """
    inicio_mes = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # SQLite guarda las fechas sin zona (ver docs/modelo-datos.md): se compara en
    # UTC «naive», que es como están escritas.
    desde = inicio_mes.replace(tzinfo=None)
    total = db.scalar(
        select(func.coalesce(func.sum(TrabajoTraduccion.num_caracteres), 0)).where(
            TrabajoTraduccion.proveedor == proveedor,
            TrabajoTraduccion.creado_en >= desde,
        )
    )
    return int(total or 0)

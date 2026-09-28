"""Modelo ORM de un trabajo de generación de subtítulo bilingüe."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum as SAEnum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import EstadoTrabajo, Idioma, ModoTrabajo


def _ahora() -> datetime:
    return datetime.now(UTC)


class TrabajoTraduccion(Base):
    """Una generación de bilingüe: por traducción (gasta cuota) o por fusión con un
    coreano existente (no la gasta). Se ejecuta en segundo plano y su progreso se
    consulta aquí.

    Es a la vez **historial**: `num_caracteres` de los trabajos terminados es lo que
    la Fase 4 agregará por proveedor y mes. Por eso sobrevive a sus subtítulos: si un
    escaneo borra el `.srt` de origen, la clave foránea pasa a nulo (`SET NULL`) pero
    el trabajo y sus rutas se conservan. Esas rutas copiadas, además, dejan la puerta
    abierta a que en la Fase 5 el origen sea una pista extraída de un MKV, que no es
    una fila de `subtitle_file`.
    """

    __tablename__ = "translation_job"

    id: Mapped[int] = mapped_column(primary_key=True)

    modo: Mapped[ModoTrabajo] = mapped_column(SAEnum(ModoTrabajo))
    estado: Mapped[EstadoTrabajo] = mapped_column(
        SAEnum(EstadoTrabajo), default=EstadoTrabajo.QUEUED, index=True
    )

    subtitulo_id: Mapped[int | None] = mapped_column(
        ForeignKey("subtitle_file.id", ondelete="SET NULL"), index=True
    )
    # Solo en modo FUSION: el coreano que se alinea con el origen.
    subtitulo_coreano_id: Mapped[int | None] = mapped_column(
        ForeignKey("subtitle_file.id", ondelete="SET NULL")
    )
    # Copia de las rutas en el momento de crear el trabajo (ver docstring).
    ruta_origen: Mapped[str] = mapped_column(String)
    ruta_coreano: Mapped[str | None] = mapped_column(String)
    ruta_bilingue: Mapped[str | None] = mapped_column(String)  # al terminar

    # El destino es siempre coreano (regla de negocio de la Fase 3).
    idioma_origen: Mapped[Idioma] = mapped_column(SAEnum(Idioma))
    proveedor: Mapped[str | None] = mapped_column(String)  # vacío en FUSION

    # Caracteres enviados al proveedor; 0 en FUSION. Alimenta la Fase 4.
    num_caracteres: Mapped[int] = mapped_column(Integer, default=0)
    calidad_alineacion: Mapped[float | None] = mapped_column(Float)  # solo en FUSION

    # Progreso para la barra del frontend.
    bloques_totales: Mapped[int] = mapped_column(Integer, default=0)
    bloques_procesados: Mapped[int] = mapped_column(Integer, default=0)

    mensaje_error: Mapped[str | None] = mapped_column(String)

    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
    iniciado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalizado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    origen: Mapped["ArchivoSubtitulo | None"] = relationship(  # noqa: F821
        foreign_keys=[subtitulo_id]
    )
    coreano: Mapped["ArchivoSubtitulo | None"] = relationship(  # noqa: F821
        foreign_keys=[subtitulo_coreano_id]
    )

    @property
    def activo(self) -> bool:
        """Si aún no ha terminado (para que el frontend siga sondeando)."""
        return self.estado in (EstadoTrabajo.QUEUED, EstadoTrabajo.RUNNING)

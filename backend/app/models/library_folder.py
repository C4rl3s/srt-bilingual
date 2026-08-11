"""Modelo ORM de una carpeta de la biblioteca a vigilar."""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _ahora() -> datetime:
    return datetime.now(UTC)


class CarpetaBiblioteca(Base):
    """Carpeta del disco que se escanea en busca de subtítulos.

    Las da de alta y de baja el usuario desde la interfaz (`/folders`). Dos carpetas
    no pueden solaparse —ninguna puede ser ancestro de otra— porque el escaneo es
    recursivo y el mismo `.srt` acabaría reclamado por las dos.

    `activa` decide si entra en el próximo escaneo; desmarcarla no borra nada, sus
    subtítulos siguen inventariados. Borrar la carpeta sí se los lleva por cascada.
    """

    __tablename__ = "library_folder"

    id: Mapped[int] = mapped_column(primary_key=True)
    ruta: Mapped[str] = mapped_column(String, unique=True, index=True)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    ultimo_escaneo: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_ahora, onupdate=_ahora
    )

    subtitulos: Mapped[list["ArchivoSubtitulo"]] = relationship(  # noqa: F821
        back_populates="carpeta",
        cascade="all, delete-orphan",
    )

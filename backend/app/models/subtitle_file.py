"""Modelo ORM de un fichero de subtítulos descubierto en una carpeta."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import EstadoSubtitulo, FormatoSubtitulo, Idioma


def _ahora() -> datetime:
    return datetime.now(UTC)


class ArchivoSubtitulo(Base):
    """Un `.srt` inventariado: su métrica (caracteres/bloques), idioma de origen,
    estado y, cuando exista, la ruta de su versión bilingüe."""

    __tablename__ = "subtitle_file"

    id: Mapped[int] = mapped_column(primary_key=True)
    carpeta_id: Mapped[int] = mapped_column(
        ForeignKey("library_folder.id", ondelete="CASCADE"), index=True
    )

    ruta: Mapped[str] = mapped_column(String, unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String)
    formato: Mapped[FormatoSubtitulo] = mapped_column(
        SAEnum(FormatoSubtitulo), default=FormatoSubtitulo.SRT
    )
    idioma_origen: Mapped[Idioma] = mapped_column(SAEnum(Idioma), default=Idioma.UNKNOWN)

    num_caracteres: Mapped[int] = mapped_column(Integer, default=0)
    num_bloques: Mapped[int] = mapped_column(Integer, default=0)

    estado: Mapped[EstadoSubtitulo] = mapped_column(
        SAEnum(EstadoSubtitulo), default=EstadoSubtitulo.PENDING, index=True
    )

    # Se rellenan en Fase 3 (o al detectar un bilingüe ya existente en disco).
    ruta_bilingue: Mapped[str | None] = mapped_column(String)
    idioma_destino: Mapped[Idioma | None] = mapped_column(SAEnum(Idioma))
    proveedor: Mapped[str | None] = mapped_column(String)

    # Detección de cambios para no reparsear lo que no cambió.
    mtime: Mapped[float] = mapped_column()
    tamano_bytes: Mapped[int] = mapped_column(Integer)

    mensaje_error: Mapped[str | None] = mapped_column(String)

    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_ahora, onupdate=_ahora
    )

    carpeta: Mapped["CarpetaBiblioteca"] = relationship(  # noqa: F821
        back_populates="subtitulos"
    )

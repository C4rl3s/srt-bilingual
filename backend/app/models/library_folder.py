"""Modelo ORM de una carpeta de la biblioteca a vigilar."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _ahora() -> datetime:
    return datetime.now(UTC)


class CarpetaBiblioteca(Base):
    """Carpeta del disco que se escanea en busca de subtítulos.

    Las carpetas se declaran en `.env` (`MEDIA_FOLDERS`) y el scanner reconcilia
    esta tabla con esa lista: crea las nuevas y **borra** las que ya no estén
    (la cascada arrastra sus subtítulos). El disco es la fuente de verdad.
    """

    __tablename__ = "library_folder"

    id: Mapped[int] = mapped_column(primary_key=True)
    ruta: Mapped[str] = mapped_column(String, unique=True, index=True)
    ultimo_escaneo: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_ahora, onupdate=_ahora
    )

    subtitulos: Mapped[list["ArchivoSubtitulo"]] = relationship(  # noqa: F821
        back_populates="carpeta",
        cascade="all, delete-orphan",
    )

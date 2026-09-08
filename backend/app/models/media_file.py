"""Modelo ORM de un fichero de vídeo descubierto en una carpeta."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _ahora() -> datetime:
    return datetime.now(UTC)


class ArchivoMedia(Base):
    """Un contenedor de vídeo inventariado (`.mkv`, `.mp4`…).

    No se abre ni se inspecciona: solo se registra su existencia, para que el árbol
    de la biblioteca pueda mostrar los capítulos aunque no tengan ningún `.srt` al
    lado. Las pistas de subtítulo embebidas son cosa de la Fase 5.
    """

    __tablename__ = "media_file"

    id: Mapped[int] = mapped_column(primary_key=True)
    carpeta_id: Mapped[int] = mapped_column(
        ForeignKey("library_folder.id", ondelete="CASCADE"), index=True
    )

    ruta: Mapped[str] = mapped_column(String, unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String)

    # Nombre sin extensión ni sufijo de idioma. Es la clave por la que el árbol
    # empareja este vídeo con sus subtítulos hermanos, así que se guarda calculada
    # para no repetir el trabajo en cada consulta.
    base: Mapped[str] = mapped_column(String, index=True)

    # Detección de cambios, mismo criterio que en `subtitle_file`.
    mtime: Mapped[float] = mapped_column()
    tamano_bytes: Mapped[int] = mapped_column(Integer)

    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_ahora, onupdate=_ahora
    )

    carpeta: Mapped["CarpetaBiblioteca"] = relationship(  # noqa: F821
        back_populates="videos"
    )

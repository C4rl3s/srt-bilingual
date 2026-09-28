"""Modelo ORM de un fichero de vídeo descubierto en una carpeta."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _ahora() -> datetime:
    return datetime.now(UTC)


class ArchivoMedia(Base):
    """Un contenedor de vídeo inventariado (`.mkv`, `.mp4`…).

    El escaneo solo registra su existencia, para que el árbol de la biblioteca pueda
    mostrar los capítulos aunque no tengan ningún `.srt` al lado. Después, en segundo
    plano, se **sondea** su cabecera con `ffprobe` y sus pistas de subtítulo pasan a
    `subtitle_file` (Fase 5, `services/mkv/sondeo.py`).
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
    # El `mtime` con que se sondearon sus pistas. Distinto del actual (o nulo): hay que
    # sondearlo. Así un vídeo sin cambios no se vuelve a abrir por la red.
    sondeado_mtime: Mapped[float | None] = mapped_column()

    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_ahora, onupdate=_ahora
    )

    carpeta: Mapped["CarpetaBiblioteca"] = relationship(  # noqa: F821
        back_populates="videos"
    )
    # Sus pistas de subtítulo. Si el vídeo desaparece, se van con él.
    pistas: Mapped[list["ArchivoSubtitulo"]] = relationship(  # noqa: F821
        back_populates="video",
        cascade="all, delete-orphan",
    )

    @property
    def pendiente_de_sondeo(self) -> bool:
        return self.sondeado_mtime != self.mtime

"""Modelo ORM de una guía de traducción (`srt-bilingual.toml`) vista en disco."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _ahora() -> datetime:
    return datetime.now(UTC)


class ArchivoGuia(Base):
    """Dónde hay una guía de traducción, según el último escaneo.

    Es **solo un índice**: su contenido se lee siempre del disco al usarla (al crear y
    al ejecutar un trabajo), así que editar el fichero no requiere escanear. Existe
    para que el árbol sepa qué obras tienen guía sin buscarla por la red, que en la
    biblioteca real cuesta 2,3 s (348 carpetas). Una guía nueva aparece en el árbol
    tras «Escanear», como un `.srt` nuevo.
    """

    __tablename__ = "guide_file"

    id: Mapped[int] = mapped_column(primary_key=True)
    carpeta_id: Mapped[int] = mapped_column(
        ForeignKey("library_folder.id", ondelete="CASCADE"), index=True
    )
    ruta: Mapped[str] = mapped_column(String, unique=True, index=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)

    carpeta: Mapped["CarpetaBiblioteca"] = relationship(  # noqa: F821
        back_populates="guias"
    )

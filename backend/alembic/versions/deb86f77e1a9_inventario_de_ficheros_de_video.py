"""inventario de ficheros de video

Crea `media_file`: el inventario de contenedores de vídeo. Permite dibujar el árbol
de la biblioteca aunque no haya ningún `.srt` (subtítulos embebidos en el MKV).

Revision ID: deb86f77e1a9
Revises: bd028a52d162
Create Date: 2026-08-11 22:59:59.877516

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "deb86f77e1a9"
down_revision: str | Sequence[str] | None = "bd028a52d162"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "media_file",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("carpeta_id", sa.Integer(), nullable=False),
        sa.Column("ruta", sa.String(), nullable=False),
        sa.Column("nombre", sa.String(), nullable=False),
        sa.Column("base", sa.String(), nullable=False),
        sa.Column("mtime", sa.Float(), nullable=False),
        sa.Column("tamano_bytes", sa.Integer(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["carpeta_id"], ["library_folder.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("media_file", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_media_file_base"), ["base"], unique=False)
        batch_op.create_index(batch_op.f("ix_media_file_carpeta_id"), ["carpeta_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_media_file_ruta"), ["ruta"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("media_file", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_media_file_ruta"))
        batch_op.drop_index(batch_op.f("ix_media_file_carpeta_id"))
        batch_op.drop_index(batch_op.f("ix_media_file_base"))

    op.drop_table("media_file")

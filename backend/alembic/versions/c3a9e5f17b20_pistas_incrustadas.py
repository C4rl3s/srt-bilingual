"""pistas incrustadas

Fase 5: las pistas de subtítulo incrustadas en un vídeo pasan a ser filas de
`subtitle_file`, con referencia a su vídeo (`video_id`, en cascada), su índice y su
título en el contenedor, si sus métricas son exactas y dónde está extraída.

`media_file.sondeado_mtime` guarda con qué `mtime` se sondearon sus pistas; los
vídeos que ya existen quedan sin sondear (nulo) y el siguiente escaneo los sondea.

`subtitle_file.formato` admite ahora los códecs de las pistas (`ASS`, `PGS`…). Las
filas que ya existen son `.srt` externos: sus métricas son exactas.

Revision ID: c3a9e5f17b20
Revises: 4447e8a4d4c5
Create Date: 2026-09-28

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3a9e5f17b20"
down_revision: str | Sequence[str] | None = "4447e8a4d4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FORMATOS_ANTES = ("SRT",)
FORMATOS_AHORA = ("SRT", "ASS", "VTT", "MOV_TEXT", "PGS", "VOBSUB")


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("media_file", schema=None) as batch_op:
        batch_op.add_column(sa.Column("sondeado_mtime", sa.Float(), nullable=True))

    with op.batch_alter_table("subtitle_file", schema=None) as batch_op:
        batch_op.alter_column(
            "formato",
            existing_type=sa.Enum(*FORMATOS_ANTES, name="formatosubtitulo"),
            type_=sa.Enum(*FORMATOS_AHORA, name="formatosubtitulo"),
            existing_nullable=False,
        )
        batch_op.add_column(sa.Column("video_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("indice_pista", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("titulo_pista", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column("metricas_exactas", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch_op.add_column(sa.Column("ruta_extraida", sa.String(), nullable=True))
        batch_op.create_index(batch_op.f("ix_subtitle_file_video_id"), ["video_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_subtitle_file_video_id_media_file",
            "media_file",
            ["video_id"],
            ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("subtitle_file", schema=None) as batch_op:
        batch_op.alter_column("metricas_exactas", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    # Las pistas no tienen sitio en el esquema anterior: se borran antes de estrecharlo.
    op.execute("DELETE FROM subtitle_file WHERE video_id IS NOT NULL")

    with op.batch_alter_table("subtitle_file", schema=None) as batch_op:
        batch_op.drop_constraint("fk_subtitle_file_video_id_media_file", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_subtitle_file_video_id"))
        batch_op.drop_column("ruta_extraida")
        batch_op.drop_column("metricas_exactas")
        batch_op.drop_column("titulo_pista")
        batch_op.drop_column("indice_pista")
        batch_op.drop_column("video_id")
        batch_op.alter_column(
            "formato",
            existing_type=sa.Enum(*FORMATOS_AHORA, name="formatosubtitulo"),
            type_=sa.Enum(*FORMATOS_ANTES, name="formatosubtitulo"),
            existing_nullable=False,
        )

    with op.batch_alter_table("media_file", schema=None) as batch_op:
        batch_op.drop_column("sondeado_mtime")

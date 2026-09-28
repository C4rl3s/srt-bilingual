"""trabajos de traduccion

Crea `translation_job`: cada generación de bilingüe, por traducción o por fusión con
un coreano existente, con su progreso y los caracteres consumidos.

Las dos claves foráneas a `subtitle_file` son `ON DELETE SET NULL`: el trabajo es
historial (lo agregará la Fase 4) y debe sobrevivir a que un escaneo borre su `.srt`.

Revision ID: b9edc39727eb
Revises: 6f170d42eb87
Create Date: 2026-09-28 12:32:57.904645

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b9edc39727eb"
down_revision: str | Sequence[str] | None = "6f170d42eb87"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "translation_job",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("modo", sa.Enum("TRADUCCION", "FUSION", name="modotrabajo"), nullable=False),
        sa.Column(
            "estado",
            sa.Enum("QUEUED", "RUNNING", "DONE", "FAILED", name="estadotrabajo"),
            nullable=False,
        ),
        sa.Column("subtitulo_id", sa.Integer(), nullable=True),
        sa.Column("subtitulo_coreano_id", sa.Integer(), nullable=True),
        sa.Column("ruta_origen", sa.String(), nullable=False),
        sa.Column("ruta_coreano", sa.String(), nullable=True),
        sa.Column("ruta_bilingue", sa.String(), nullable=True),
        sa.Column(
            "idioma_origen",
            sa.Enum("ES", "EN", "KO", "FR", "DE", "IT", "PT", "JA", "ZH", "UNKNOWN", name="idioma"),
            nullable=False,
        ),
        sa.Column("proveedor", sa.String(), nullable=True),
        sa.Column("num_caracteres", sa.Integer(), nullable=False),
        sa.Column("calidad_alineacion", sa.Float(), nullable=True),
        sa.Column("bloques_totales", sa.Integer(), nullable=False),
        sa.Column("bloques_procesados", sa.Integer(), nullable=False),
        sa.Column("mensaje_error", sa.String(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("iniciado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["subtitulo_coreano_id"], ["subtitle_file.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["subtitulo_id"], ["subtitle_file.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("translation_job", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_translation_job_estado"), ["estado"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_translation_job_subtitulo_id"), ["subtitulo_id"], unique=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("translation_job", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_translation_job_subtitulo_id"))
        batch_op.drop_index(batch_op.f("ix_translation_job_estado"))

    op.drop_table("translation_job")

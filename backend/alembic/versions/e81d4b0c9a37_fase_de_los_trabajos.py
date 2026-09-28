"""fase de los trabajos

Añade `translation_job.fase`: en qué está un trabajo en curso. Con los orígenes que
son pistas incrustadas (Fase 5), antes de generar hay que extraerlas del vídeo, y eso
por la red tarda 1–1,5 min por episodio sin progreso de bloques que enseñar.

Nula en los trabajos que ya existen: están terminados.

Revision ID: e81d4b0c9a37
Revises: c3a9e5f17b20
Create Date: 2026-09-28

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e81d4b0c9a37"
down_revision: str | Sequence[str] | None = "c3a9e5f17b20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("translation_job", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("fase", sa.Enum("EXTRAYENDO", "GENERANDO", name="fasetrabajo"), nullable=True)
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("translation_job", schema=None) as batch_op:
        batch_op.drop_column("fase")

"""caracteres previstos de los trabajos

Añade `translation_job.caracteres_previstos`: lo que se espera enviar al proveedor,
fijado al crear el trabajo. Mientras está en cola o en curso, lo que falta por
enviar queda reservado del cupo (Fase 4).

Los trabajos que ya existen quedan con 0: están terminados y no reservan nada.

Revision ID: 4447e8a4d4c5
Revises: b9edc39727eb
Create Date: 2026-09-28

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4447e8a4d4c5"
down_revision: str | Sequence[str] | None = "b9edc39727eb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("translation_job", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("caracteres_previstos", sa.Integer(), nullable=False, server_default="0")
        )

    with op.batch_alter_table("translation_job", schema=None) as batch_op:
        batch_op.alter_column("caracteres_previstos", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("translation_job", schema=None) as batch_op:
        batch_op.drop_column("caracteres_previstos")

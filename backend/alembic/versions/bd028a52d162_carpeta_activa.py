"""carpeta activa

Añade `library_folder.activa`: si la carpeta entra en el próximo escaneo.

Se crea con `server_default` para poder rellenar las filas que ya existan (la
columna es NOT NULL) y se retira justo después, de modo que el valor por defecto
viva solo en el modelo Python y no en el esquema.

Revision ID: bd028a52d162
Revises: 4684c713e94f
Create Date: 2026-08-11 22:19:33.329362

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bd028a52d162"
down_revision: str | Sequence[str] | None = "4684c713e94f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("library_folder", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.true())
        )

    with op.batch_alter_table("library_folder", schema=None) as batch_op:
        batch_op.alter_column("activa", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("library_folder", schema=None) as batch_op:
        batch_op.drop_column("activa")

"""flags forzado y sdh y version de analisis

Añade a `subtitle_file`:

- `es_forzado` y `es_sdh`: flags declarados en el nombre del subtítulo.
- `version_analisis`: versión de las reglas de análisis con que se procesó la fila.

Las filas que ya existan quedan con `version_analisis = 0`, así que el siguiente
escaneo las reprocesa con las reglas nuevas (idioma por contenido y flags) aunque el
fichero no haya cambiado en disco.

Como en `carpeta_activa`, el `server_default` solo sirve para rellenar las filas
existentes (las columnas son NOT NULL) y se retira justo después: el valor por
defecto vive en el modelo Python, no en el esquema.

Revision ID: 6f170d42eb87
Revises: deb86f77e1a9
Create Date: 2026-09-28 11:00:02.749520

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6f170d42eb87"
down_revision: str | Sequence[str] | None = "deb86f77e1a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("subtitle_file", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("es_forzado", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column("es_sdh", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column("version_analisis", sa.Integer(), nullable=False, server_default="0")
        )

    with op.batch_alter_table("subtitle_file", schema=None) as batch_op:
        batch_op.alter_column("es_forzado", server_default=None)
        batch_op.alter_column("es_sdh", server_default=None)
        batch_op.alter_column("version_analisis", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("subtitle_file", schema=None) as batch_op:
        batch_op.drop_column("version_analisis")
        batch_op.drop_column("es_sdh")
        batch_op.drop_column("es_forzado")

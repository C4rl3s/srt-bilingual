"""Entorno de ejecución de Alembic.

Se aparta de la plantilla por defecto en dos cosas:

1. La URL de la base de datos **no** se lee de `alembic.ini`, sino de
   `app.config.settings` (misma fuente que la app: un solo sitio que tocar).
2. `target_metadata` apunta a `Base.metadata` importando `app.models`, para que
   `--autogenerate` vea las tablas del proyecto.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Importar `app.models` registra todos los modelos en `Base.metadata`; sin este
# import, autogenerate no vería ninguna tabla.
import app.models  # noqa: F401
from app.config import settings
from app.db import Base

# Objeto de configuración de Alembic (da acceso a los valores de alembic.ini).
config = context.config

# Configuración del logging declarada en el .ini.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# La URL efectiva es siempre la de la app, no la del .ini.
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Genera el SQL de las migraciones sin conectarse a la base de datos."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite apenas soporta ALTER TABLE: en "batch mode" Alembic emula los
        # cambios recreando la tabla y copiando los datos.
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Aplica las migraciones contra la base de datos real."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

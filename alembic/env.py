import os
import sys

sys.path.insert(0, os.getcwd())

from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# bring in your MetaData
from models import Base  # <-- wherever you put your declarative Base

config = context.config

# logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# **inject the URL from the environment** **
db_url = os.getenv("DATABASE_URL")
if not db_url:
    raise RuntimeError("DATABASE_URL environment variable not set")
config.set_main_option("sqlalchemy.url", db_url)

# point Alembic at your models
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

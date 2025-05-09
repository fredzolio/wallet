import os
import sys
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection

from alembic import context

# Adicionar diretório raiz ao path do Python para permitir importações do pacote app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# esse é o objeto Alembic MetaData para a declaração de tabelas.
# inclui todas as tabelas MetaData da aplicação.
from app.db.base import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# interpreta o arquivo config e configura o logging
fileConfig(config.config_file_name)

# adiciona o MetaData do modelo
target_metadata = Base.metadata

# outras configurações, definidas em alembic.ini
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgresql+asyncpg://"):
    # Converte a URL assíncrona para síncrona para o Alembic
    SQLALCHEMY_DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
else:
    SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))

config.set_main_option("sqlalchemy.url", SQLALCHEMY_DATABASE_URL)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Função para executar as migrações com uma conexão existente"""
    context.configure(
        connection=connection,
        target_metadata=target_metadata
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    # Configuração do engine síncrono para Alembic
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online() 
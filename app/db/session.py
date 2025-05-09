from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.core.config import settings

# Configuração do engine SQLAlchemy
engine = create_async_engine(
    settings.database_url,  # Usando a propriedade que criamos
    pool_pre_ping=True,  # Verifica se a conexão está ativa antes de usar
    echo=False,  # Desativa logs de SQL em produção
)

# Session factory usando async_sessionmaker que é apropriado para AsyncEngine
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

# Dependência para obter uma sessão de banco de dados
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependência que fornece uma sessão de banco de dados assíncrona.
    A sessão é fechada automaticamente após o uso.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

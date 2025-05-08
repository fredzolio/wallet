from sqlalchemy.ext.asyncio import AsyncSession
import logging
from sqlalchemy import select

from app.db.base import Base
from app.db.session import engine
from app.models.user import User
from app.core.security import hash_password

logger = logging.getLogger(__name__)

async def init_db(db: AsyncSession) -> None:
    """
    Inicializa o banco de dados com dados iniciais.
    Essa função é chamada durante a inicialização da aplicação.
    """
    logger.info("Garantindo que todas as tabelas foram criadas...")
    async with engine.begin() as conn:
        # Esta linha garante que todas as tabelas definidas em Base.metadata sejam criadas
        # se ainda não existirem. É uma salvaguarda caso as migrações do Alembic
        # não tenham sido executadas ou estejam incompletas.
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Tabelas verificadas/criadas.")

    # Verificar se já existem usuários
    result = await db.execute(select(User).limit(1))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        logger.info("Banco de dados já inicializado com dados básicos (usuário admin), pulando seed do admin.")
        return

    logger.info("Criando usuário admin inicial")
    admin_user = User(
        email="admin@example.com",
        hashed_password=hash_password("adminpassword"),
        is_active=True
    )
    
    db.add(admin_user)
    await db.commit()
    
    logger.info("Banco de dados inicializado com sucesso")

async def seed_db(db: AsyncSession) -> None:
    """
    Popula o banco de dados com dados de exemplo para desenvolvimento.
    Esta função só deve ser chamada em ambiente de desenvolvimento.
    """
    # Verificar se já existem usuários de exemplo
    result = await db.execute(select(User).where(User.email == "teste@example.com"))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        logger.info("Dados de exemplo já existem, pulando seed")
        return
    
    logger.info("Criando dados de exemplo")
    
    # Criar usuário de teste
    test_user = User(
        email="teste@example.com",
        hashed_password=hash_password("teste123"),
        is_active=True
    )
    
    db.add(test_user)
    await db.commit()
    await db.refresh(test_user)
    
    logger.info("Dados de exemplo criados com sucesso") 
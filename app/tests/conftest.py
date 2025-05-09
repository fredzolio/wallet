import pytest
import pytest_asyncio
import asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
import fakeredis.aioredis
from typing import AsyncGenerator, Dict
from unittest.mock import patch
import logging

from app.core.config import settings as app_settings
from app.db.base_class import Base as BaseImported
from app.models.user import User
from app.core.security import hash_password, create_access_token
from app.main import app
from app.db.session import get_db
from app.api.v1.deps import redis as app_redis_global

# Imports para SlowAPI
from slowapi import Limiter as SlowAPILimiter_local
from slowapi.util import get_remote_address as slowapi_get_remote_address

from redis.asyncio import Redis as ActualAsyncRedis

# Sobrescreve a URL do banco para usar SQLite em memória
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Cria engine e session para testes
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = async_sessionmaker(
    bind=test_engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

# Remove a instância global de fake_redis daqui
# fake_redis = fakeredis.aioredis.FakeRedis()

# Substitui as dependências reais por mock para testes
async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session

# Sobrescreve as dependências no app para testes
app.dependency_overrides[get_db] = override_get_db
# app.dependency_overrides[app_redis_global] = lambda: fake_redis # Linha original comentada/removida

@pytest.fixture(scope="session", autouse=True)
def setup_google_oauth_for_session():
    """
    Garante que as settings do Google OAuth estejam definidas para a sessão de teste
    e que o cliente 'google' seja registrado no objeto oauth global.
    """
    with patch('app.core.config.settings.GOOGLE_CLIENT_ID', 'test_google_client_id'), \
         patch('app.core.config.settings.GOOGLE_CLIENT_SECRET', 'test_google_client_secret_key'):
        
        from app.core.security import oauth as security_oauth_instance
        # As settings já devem estar mockadas quando security.py é importado
        # pela primeira vez ou quando o objeto oauth é usado.
        # A Authlib registra o cliente quando `oauth.register` é chamado.
        # Se security.py já foi importado e `oauth.register` chamado sem as settings,
        # o cliente 'google' não existirá.
        # Forçar o registro aqui se ele não ocorreu pode ser uma solução.

        # Se o registro condicional em security.py já ocorreu (sem as settings),
        # `oauth.google` não existirá. Vamos tentar registrar aqui explicitamente
        # com as settings agora mockadas.
        if not hasattr(security_oauth_instance, 'google'):
            # Precisamos garantir que app_settings_instance aqui reflita os patches
            # O ideal é que o patch seja aplicado antes de security.py ser importado.
            # Dado que esta fixture é session-scoped e autouse, ela deve executar cedo.
            
            # Re-acessar as settings mockadas (elas são globais no módulo config)
            from app.core.config import settings as patched_app_settings 
            
            security_oauth_instance.register(
                name="google",
                client_id=patched_app_settings.GOOGLE_CLIENT_ID,
                client_secret=patched_app_settings.GOOGLE_CLIENT_SECRET,
                server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
                client_kwargs={"scope": "openid email profile"},
            )
        
        yield
        
        # Limpeza opcional: Se o cliente 'google' foi adicionado dinamicamente
        # pelo teste e não faz parte da configuração padrão sem settings,
        # podemos tentar removê-lo para evitar interferência entre sessões (embora raro com pytest).
        # Nota: A Authlib não tem um método público `unregister` simples.
        # Remover atributos diretamente pode ser arriscado.
        # É melhor garantir que os testes sejam isolados ou que o estado seja resetado.
        if hasattr(security_oauth_instance, '_clients') and 'google' in security_oauth_instance._clients:
             security_oauth_instance._clients.pop('google', None) # Use pop com default
        if hasattr(security_oauth_instance, 'google'):
            try:
                delattr(security_oauth_instance, 'google')
            except AttributeError:
                pass # Já pode ter sido removido ou não existir mais

@pytest_asyncio.fixture(scope="function")
async def test_redis() -> AsyncGenerator[fakeredis.aioredis.FakeRedis, None]:
    """Fornece uma instância de FakeRedis para cada teste e garante o fechamento."""
    instance = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await instance.flushall()
    yield instance
    await asyncio.sleep(0.01) # Pequeno sleep antes de fechar
    try:
        await instance.aclose()
    except RuntimeError as e:
        logger = logging.getLogger(__name__)
        if "event loop is closed" in str(e).lower():
            logger.warning(f"Fakeredis aclose() encontrou 'event loop is closed' durante o teardown da fixture test_redis: {e}")
        else:
            logger.error(f"RuntimeError inesperado durante o test_redis aclose: {e}")
            raise
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Exceção inesperada durante o test_redis aclose: {e}")
        raise
    await asyncio.sleep(0.01) # Pequeno sleep depois de fechar

@pytest_asyncio.fixture(scope="function")
async def init_test_db() -> AsyncGenerator[None, None]:
    """Inicializa o banco de testes."""
    async with test_engine.begin() as conn:
        await conn.run_sync(BaseImported.metadata.create_all)
    
    yield
    
    async with test_engine.begin() as conn:
        await conn.run_sync(BaseImported.metadata.drop_all)

@pytest_asyncio.fixture
async def db_session(init_test_db) -> AsyncGenerator[AsyncSession, None]:
    """Fornece uma sessão de banco de dados para testes."""
    async with TestingSessionLocal() as session:
        yield session
        # O rollback aqui pode não ser mais estritamente necessário 
        # se as tabelas são derrubadas após cada teste, mas não prejudica.
        await session.rollback()

@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession, test_redis: fakeredis.aioredis.FakeRedis) -> AsyncGenerator[AsyncClient, None]:
    """Fornece um cliente HTTP assíncrono para testes."""
    
    original_app_redis_override = app.dependency_overrides.get(app_redis_global)
    app.dependency_overrides[app_redis_global] = lambda: test_redis

    # Configuração do Limiter: Como test_redis agora é um AsyncMock,
    # o patch de Redis.from_url é crucial e deve retornar este mock.
    original_redis_from_url = ActualAsyncRedis.from_url

    def _mock_redis_from_url(cls, url, **options):
        # O SlowAPI/limits vai chamar Redis.from_url(). Precisamos que ele use nosso mock_redis.
        return test_redis 

    ActualAsyncRedis.from_url = classmethod(_mock_redis_from_url)

    test_limiter_uri = f"redis://{app_settings.REDIS_HOST}:{app_settings.REDIS_PORT}/0"
    
    # Esta instanciação do Limiter agora usará test_redis (AsyncMock) via o patch acima.
    # Se o AsyncMock não simular evalsha/pipeline corretamente, o SlowAPI pode falhar.
    test_limiter_instance = SlowAPILimiter_local(
        key_func=slowapi_get_remote_address,
        storage_uri=test_limiter_uri 
    )

    ActualAsyncRedis.from_url = original_redis_from_url # Restaurar imediatamente

    original_app_state_limiter = getattr(app.state, "limiter", None)
    app.state.limiter = test_limiter_instance

    limiter_module_paths = [
        "app.api.v1.endpoints.auth.limiter",
        "app.api.v1.endpoints.documents.limiter",
        "app.api.v1.endpoints.transport.limiter",
        "app.api.v1.endpoints.chatbot.limiter",
    ]
    active_limiter_patches = []
    logger = logging.getLogger(__name__)
    for path_to_patch in limiter_module_paths:
        try:
            p = patch(path_to_patch, test_limiter_instance)
            p.start()
            active_limiter_patches.append(p)
        except (ModuleNotFoundError, AttributeError):
            logger.warning(f"Não foi possível aplicar patch no limiter em {path_to_patch}. Módulo ou atributo não encontrado.")
            pass
            
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    
    # Aumentar este sleep significativamente para diagnóstico
    await asyncio.sleep(0.5) # Aumentado de 0.1 para 0.5

    # --- Restauração (após o sleep) ---
    for p in active_limiter_patches:
        p.stop()
    
    if original_app_state_limiter is not None:
        app.state.limiter = original_app_state_limiter
    elif hasattr(app.state, "limiter"): # Se adicionamos e não existia, remove
        delattr(app.state, "limiter")

    if original_app_redis_override is not None:
        app.dependency_overrides[app_redis_global] = original_app_redis_override
    else:
        app.dependency_overrides.pop(app_redis_global, None)

@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Cria um usuário de teste."""
    user = User(
        email="test@example.com",
        hashed_password=hash_password("testpassword"),
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest_asyncio.fixture
async def test_superuser(db_session: AsyncSession) -> User:
    """Cria um super usuário de teste."""
    user = User(
        email="admin@example.com",
        hashed_password=hash_password("adminpassword"),
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest_asyncio.fixture
async def user_token_headers(test_user: User) -> Dict[str, str]:
    """Retorna headers com token de autenticação para o usuário de teste."""
    access_token = create_access_token(test_user.id)
    return {"Authorization": f"Bearer {access_token}"}

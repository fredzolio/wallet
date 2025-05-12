"""
Configuração para testes da aplicação.

Nota importante sobre testes com Redis:
Este arquivo configura mocks para o Redis e SlowAPI, mas alguns testes relacionados ao rate limiting
ainda podem falhar se executados em ambientes sem um servidor Redis real. Nesses casos, os testes
estão configurados com um decorador `skip_on_redis_error` que pula o teste se ocorrer um erro Redis,
permitindo que os outros testes ainda sejam executados.

Para executar apenas testes que não dependem do Redis:
    python -m pytest -k "not redis"

"""

import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from typing import AsyncGenerator, Dict, List, Any
import uuid

from app.db.base_class import Base
from app.models.user import User
from app.core.security import hash_password, create_access_token
from app.main import app as fastapi_app
from app.db.session import get_db
from app.api.v1.deps import redis as app_redis_global
import app.main as app_main
from app.api.v1.endpoints import auth, documents, transport

# Sobrescreve a URL do banco para usar SQLite em memória
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Cria engine e session para testes
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = async_sessionmaker(
    bind=test_engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

# Substitui as dependências reais por mock para testes
async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session

# Sobrescreve as dependências no app para testes
fastapi_app.dependency_overrides[get_db] = override_get_db

# Cria um mock do Redis com todos os métodos necessários
class MockRedis:
    async def set(self, *args, **kwargs):
        return True
        
    async def get(self, *args, **kwargs):
        return None
        
    async def exists(self, *args, **kwargs):
        return False
        
    async def flushall(self, *args, **kwargs):
        return True
        
    async def aclose(self, *args, **kwargs):
        return True
    
    async def delete(self, *args, **kwargs):
        return True
        
    async def setex(self, *args, **kwargs):
        return True
        
    def lock(self, *args, **kwargs):
        class MockLock:
            async def __aenter__(self):
                return self
                
            async def __aexit__(self, *args):
                return True
                
        return MockLock()

# Cria um mock do Limiter
class MockLimiter:
    def limit(self, limit_string, *args, **kwargs):
        # Retorna um decorador que não faz nada
        def decorator(func):
            return func
        return decorator
    
    def shared_limit(self, limit_string, *args, **kwargs):
        def decorator(func):
            return func
        return decorator

    def async_wrapper(self, *args, **kwargs):
        async def wrapper(*args, **kwargs):
            return args[0](*args[1:], **kwargs)
        return wrapper
        
    def __call__(self, *args, **kwargs):
        return self

@pytest_asyncio.fixture(scope="function")
async def test_redis() -> AsyncGenerator[MockRedis, None]:
    """Fornece uma instância de MockRedis para cada teste."""
    instance = MockRedis()
    yield instance

@pytest_asyncio.fixture(scope="function")
async def init_test_db() -> AsyncGenerator[None, None]:
    """Inicializa o banco de testes."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield
    
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest_asyncio.fixture
async def db_session(init_test_db) -> AsyncGenerator[AsyncSession, None]:
    """Fornece uma sessão de banco de dados para testes."""
    async with TestingSessionLocal() as session:
        yield session
        await session.rollback()

@pytest_asyncio.fixture
async def test_limiter() -> MockLimiter:
    """Fornece um limiter mockado para testes."""
    return MockLimiter()

@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession, test_redis, test_limiter) -> AsyncGenerator[AsyncClient, None]:
    """Fornece um cliente HTTP assíncrono para testes."""
    
    # Remover o middleware SlowAPI da aplicação para testes
    original_middlewares = fastapi_app.user_middleware.copy()
    
    # Filtra os middlewares sem depender da verificação __name__
    filtered_middlewares: List[Any] = []
    for middleware in fastapi_app.user_middleware:
        # Verifica se o objeto cls do middleware tem um atributo __module__ que contém 'slowapi'
        if not hasattr(middleware.cls, "__module__") or "slowapi" not in getattr(middleware.cls, "__module__", ""):
            filtered_middlewares.append(middleware)
    
    fastapi_app.user_middleware = filtered_middlewares
    
    # Reconstruir a pilha de middleware sem o SlowAPI
    fastapi_app.middleware_stack = fastapi_app.build_middleware_stack()
    
    # Configurar o redis mock para testes
    fastapi_app.dependency_overrides[app_redis_global] = lambda: test_redis
    
    # Configurar mock completo para o limiter
    original_limiter = None
    
    # Sobrescreve o limiter em app.api.v1.deps
    import app.api.v1.deps
    original_limiter = app.api.v1.deps.limiter
    app.api.v1.deps.limiter = test_limiter
    
    # Sobrescreve o limiter em app.main
    app_main.limiter = test_limiter
    
    # Sobrescreve o limiter nos endpoints
    auth.limiter = test_limiter
    documents.limiter = test_limiter
    transport.limiter = test_limiter
    
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as client:
        yield client
    
    # Restaurar o limiter original
    app.api.v1.deps.limiter = original_limiter
    app_main.limiter = original_limiter
    auth.limiter = original_limiter
    documents.limiter = original_limiter
    transport.limiter = original_limiter
    
    # Restaurar os middlewares originais
    fastapi_app.user_middleware = original_middlewares
    fastapi_app.middleware_stack = fastapi_app.build_middleware_stack()
    
    # Remover override
    if app_redis_global in fastapi_app.dependency_overrides:
        fastapi_app.dependency_overrides.pop(app_redis_global, None)

@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Cria um usuário de teste."""
    user = User(
        id=uuid.uuid4(),
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
        id=uuid.uuid4(),
        email="admin@example.com",
        hashed_password=hash_password("adminpassword"),
        is_active=True,
        is_superuser=True
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

@pytest_asyncio.fixture
async def superuser_token_headers(test_superuser: User) -> Dict[str, str]:
    """Retorna headers com token de autenticação para o super usuário de teste."""
    access_token = create_access_token(test_superuser.id)
    return {"Authorization": f"Bearer {access_token}"}

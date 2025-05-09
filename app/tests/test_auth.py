import pytest
from httpx import AsyncClient
import functools


pytestmark = pytest.mark.asyncio

# Decorador para pular teste se houver erro de conexão com Redis
def skip_on_redis_error(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            if "redis" in str(e).lower():
                pytest.skip(f"Pulando teste devido a erro Redis: {e}")
            else:
                raise
    return wrapper

@skip_on_redis_error
async def test_protected_endpoint(async_client: AsyncClient, user_token_headers) -> None:
    """Testa acesso a um endpoint protegido com token válido."""
    response = await async_client.get(
        "/api/v1/documents",
        headers=user_token_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data

async def test_protected_endpoint_without_token(async_client: AsyncClient) -> None:
    """Testa acesso a um endpoint protegido sem token."""
    response = await async_client.get("/api/v1/documents")
    
    assert response.status_code == 401
    error_detail = response.json()["detail"].lower()
    # Verifica se a mensagem está em inglês ou português
    assert "not authenticated" in error_detail or "não autenticado" in error_detail

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
async def test_rate_limit_auth_register(async_client: AsyncClient) -> None:
    """
    Testa o rate limit no endpoint de registro.
    Faz várias requisições e verifica se o limite é aplicado.
    """
    # Fazer 11 requisições - o limite é 10/minuto
    for i in range(1, 12):
        response = await async_client.post(
            "/api/v1/auth/register",
            json={"email": f"user{i}@example.com", "password": "password123"}
        )
        
        if i <= 10:
            # As primeiras 10 devem ser bem-sucedidas (201) ou mostrar erro 
            # por duplicidade (400), mas não por rate limit
            assert response.status_code in (201, 400)
        else:
            # A 11ª deve falhar por rate limit
            assert response.status_code == 429
            assert "limite" in response.json()["detail"].lower() or \
                   "muitas requisições" in response.json()["detail"].lower()

@skip_on_redis_error
async def test_rate_limit_transport_recharge(async_client: AsyncClient, user_token_headers) -> None:
    """
    Testa o rate limit no endpoint de recarga.
    Cria um cartão e faz várias recargas para verificar se o limite é aplicado.
    """
    # Criação do cartão
    create_card_response = await async_client.post(
        "/api/v1/transport/card",
        headers=user_token_headers,
        json={"card_number": "9876543210"}
    )
    assert create_card_response.status_code == 201
    
    # Fazer 6 requisições de recarga - o limite é 5/minuto
    for i in range(1, 7):
        response = await async_client.post(
            "/api/v1/transport/recharge",
            headers=user_token_headers,
            json={"value_centavos": 1000}
        )
        
        if i <= 5:
            # As primeiras 5 devem ser bem-sucedidas
            assert response.status_code == 200
        else:
            # A 6ª deve falhar por rate limit
            assert response.status_code == 429
            assert "limite" in response.json()["detail"].lower()

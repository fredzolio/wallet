import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
import random
import string
import functools

from app.models.transport import TransportCard
from app.models.recarga import Recarga
from app.models.user import User

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

def generate_card_number():
    """Gera um número aleatório de cartão para testes."""
    return ''.join(random.choices(string.digits, k=16))

@skip_on_redis_error
async def test_create_transport_card(async_client: AsyncClient, user_token_headers) -> None:
    """Testa a criação de um novo cartão de transporte."""
    card_number = generate_card_number()
    response = await async_client.post(
        "/api/v1/transport/card",
        headers=user_token_headers,
        json={"card_number": card_number}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["card_number"] == card_number
    assert data["balance_centavos"] == 0
    assert "id" in data
    assert "user_id" in data

@skip_on_redis_error
async def test_create_duplicate_card(async_client: AsyncClient, user_token_headers) -> None:
    """Testa a criação de um cartão duplicado para o mesmo usuário."""
    card_number = generate_card_number()
    await async_client.post(
        "/api/v1/transport/card",
        headers=user_token_headers,
        json={"card_number": card_number}
    )
    response = await async_client.post(
        "/api/v1/transport/card",
        headers=user_token_headers,
        json={"card_number": generate_card_number()}
    )
    assert response.status_code == 400
    assert "já possui um cartão" in response.json()["detail"].lower()

@skip_on_redis_error
async def test_get_card(async_client: AsyncClient, db_session: AsyncSession, user_token_headers, test_user: User) -> None:
    """Testa a obtenção dos dados do cartão de transporte."""
    card_number = generate_card_number()
    card = TransportCard(
        id=uuid.uuid4(),
        user_id=test_user.id,
        card_number=card_number,
        balance_centavos=1000
    )
    db_session.add(card)
    await db_session.commit()

    response = await async_client.get(
        "/api/v1/transport/card",
        headers=user_token_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["card_number"] == card_number
    assert data["balance_centavos"] == 1000

@skip_on_redis_error
async def test_get_balance(async_client: AsyncClient, db_session: AsyncSession, user_token_headers, test_user: User) -> None:
    """Testa a consulta de saldo do cartão de transporte."""
    card_number = generate_card_number()
    card = TransportCard(
        id=uuid.uuid4(),
        user_id=test_user.id,
        card_number=card_number,
        balance_centavos=2500
    )
    db_session.add(card)
    await db_session.commit()

    response = await async_client.get(
        "/api/v1/transport/balance",
        headers=user_token_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["balance_centavos"] == 2500
    assert data["balance_reais"] == 25.0
    assert data["card_number"] == card_number

@skip_on_redis_error
async def test_list_recharges(async_client: AsyncClient, db_session: AsyncSession, user_token_headers, test_user: User) -> None:
    """Testa a listagem do histórico de recargas."""
    card_number = generate_card_number()
    card = TransportCard(
        id=uuid.uuid4(),
        user_id=test_user.id,
        card_number=card_number,
        balance_centavos=0
    )
    db_session.add(card)
    await db_session.commit()
    
    # Adicionar algumas recargas
    recargas_data = [
        {"card_id": card.id, "value_centavos": 1000, "id": uuid.uuid4()},
        {"card_id": card.id, "value_centavos": 2000, "id": uuid.uuid4()},
        {"card_id": card.id, "value_centavos": 3000, "id": uuid.uuid4()}
    ]
    for rec_data in recargas_data:
        recarga = Recarga(**rec_data)
        db_session.add(recarga)
    await db_session.commit()

    response = await async_client.get(
        "/api/v1/transport/recharges",
        headers=user_token_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] == 3
    assert len(data["items"]) == 3 
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid
import functools

from app.models.document import Document
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

@skip_on_redis_error
async def test_list_documents(async_client: AsyncClient, db_session: AsyncSession, user_token_headers, test_user: User) -> None:
    """Testa a listagem de documentos."""
    # Criar documentos para o teste
    for i in range(3):
        doc = Document(
            id=uuid.uuid4(),
            user_id=test_user.id,
            type=f"tipo_{i}",
            content_json={"data": f"conteúdo {i}"}
        )
        db_session.add(doc)
    await db_session.commit()
    
    response = await async_client.get(
        "/api/v1/documents",
        headers=user_token_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 3

@skip_on_redis_error
async def test_list_documents_with_filter(async_client: AsyncClient, db_session: AsyncSession, user_token_headers, test_user: User) -> None:
    """Testa a listagem de documentos com filtro por tipo."""
    doc = Document(
        id=uuid.uuid4(),
        user_id=test_user.id,
        type="rg",
        content_json={"numero": "12.345.678-9"}
    )
    db_session.add(doc)
    await db_session.commit()

    response = await async_client.get(
        "/api/v1/documents?type=rg",
        headers=user_token_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    for item in data["items"]:
        assert item["type"] == "rg"

@skip_on_redis_error
async def test_get_document(async_client: AsyncClient, db_session: AsyncSession, user_token_headers, test_user: User) -> None:
    """Testa a obtenção de um documento específico."""
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        user_id=test_user.id,
        type="cnh",
        content_json={"numero": "123456789", "categoria": "AB"}
    )
    db_session.add(doc)
    await db_session.commit()

    response = await async_client.get(
        f"/api/v1/documents/{str(doc_id)}",
        headers=user_token_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(doc_id)
    assert data["type"] == "cnh"
    assert data["content_json"]["numero"] == "123456789"

@skip_on_redis_error
async def test_update_document(async_client: AsyncClient, db_session: AsyncSession, user_token_headers, test_user: User) -> None:
    """Testa a atualização de um documento."""
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        user_id=test_user.id,
        type="comprovante_residencia",
        content_json={"endereco": "Rua Antiga, 123"}
    )
    db_session.add(doc)
    await db_session.commit()

    response = await async_client.put(
        f"/api/v1/documents/{str(doc_id)}",
        headers=user_token_headers,
        json={
            "type": "comprovante_residencia",
            "content_json": {"endereco": "Rua Nova, 456"}
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["content_json"]["endereco"] == "Rua Nova, 456"

@skip_on_redis_error
async def test_delete_document(async_client: AsyncClient, db_session: AsyncSession, user_token_headers, test_user: User) -> None:
    """Testa a exclusão de um documento."""
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        user_id=test_user.id,
        type="cartao_vacina",
        content_json={"vacinas": ["Covid-19", "Influenza"]}
    )
    db_session.add(doc)
    await db_session.commit()

    response = await async_client.delete(
        f"/api/v1/documents/{str(doc_id)}",
        headers=user_token_headers
    )
    assert response.status_code == 204
    
    # Verificar que o documento foi excluído
    result = await db_session.execute(select(Document).where(Document.id == doc_id))
    assert result.scalar_one_or_none() is None

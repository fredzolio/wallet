import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict
import uuid

from app.models.document import Document
from app.models.user import User

pytestmark = pytest.mark.asyncio

async def test_create_document(async_client: AsyncClient, user_token_headers: Dict[str, str]) -> None:
    """Testa a criação de um novo documento."""
    response = await async_client.post(
        "/api/v1/documents",
        headers=user_token_headers,
        json={
            "type": "cpf",
            "content_json": {"numero": "123.456.789-00", "nome": "Usuário de Teste"}
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "cpf"
    assert data["content_json"]["numero"] == "123.456.789-00"
    assert data["content_json"]["nome"] == "Usuário de Teste"
    assert "id" in data
    assert "user_id" in data
    assert "created_at" in data

async def test_create_document_rate_limit(async_client: AsyncClient, user_token_headers: Dict[str, str]) -> None:
    """Testa o rate limiting na criação de documentos."""
    for i in range(30):
        await async_client.post(
            "/api/v1/documents",
            headers=user_token_headers,
            json={
                "type": f"doc_{i}",
                "content_json": {"data": f"conteúdo {i}"}
            }
        )
    response = await async_client.post(
        "/api/v1/documents",
        headers=user_token_headers,
        json={
            "type": "doc_extra",
            "content_json": {"data": "conteúdo extra"}
        }
    )
    assert response.status_code == 429

async def test_list_documents(async_client: AsyncClient, db_session: AsyncSession, user_token_headers: Dict[str, str], test_user: User) -> None:
    """Testa a listagem de documentos."""
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
    doc_types = [item["type"] for item in data["items"]]
    assert "tipo_0" in doc_types
    assert "tipo_1" in doc_types
    assert "tipo_2" in doc_types

async def test_list_documents_with_filter(async_client: AsyncClient, db_session: AsyncSession, user_token_headers: Dict[str, str], test_user: User) -> None:
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
    assert "total" in data
    assert data["total"] >= 1
    for item in data["items"]:
        assert item["type"] == "rg"

async def test_get_document(async_client: AsyncClient, db_session: AsyncSession, user_token_headers: Dict[str, str], test_user: User) -> None:
    """Testa a obtenção de um documento específico."""
    doc_id_obj = uuid.uuid4()
    doc = Document(
        id=doc_id_obj,
        user_id=test_user.id,
        type="cnh",
        content_json={"numero": "123456789", "categoria": "AB"}
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    response = await async_client.get(
        f"/api/v1/documents/{str(doc_id_obj)}",
        headers=user_token_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(doc_id_obj)
    assert data["type"] == "cnh"
    assert data["content_json"]["numero"] == "123456789"
    assert data["content_json"]["categoria"] == "AB"

async def test_get_nonexistent_document(async_client: AsyncClient, user_token_headers: Dict[str, str]) -> None:
    """Testa a tentativa de obter um documento inexistente."""
    non_existent_uuid = uuid.uuid4()
    response = await async_client.get(
        f"/api/v1/documents/{non_existent_uuid}",
        headers=user_token_headers
    )
    assert response.status_code == 404
    # O detalhe pode variar dependendo se o ID é inválido (422) ou não encontrado (404)
    # Para um UUID válido mas não encontrado, esperamos "Documento não encontrado"
    assert "não encontrado" in response.json()["detail"].lower()

async def test_get_other_user_document(async_client: AsyncClient, db_session: AsyncSession, user_token_headers: Dict[str, str]) -> None:
    """Testa a tentativa de obter um documento de outro usuário."""
    other_user = User(
        email="other@example.com",
        hashed_password="hashedpassword",
        is_active=True
    )
    db_session.add(other_user)
    await db_session.commit()
    await db_session.refresh(other_user)
    
    doc_id_obj = uuid.uuid4()
    doc = Document(
        id=doc_id_obj,
        user_id=other_user.id,
        type="passaporte",
        content_json={"numero": "AB123456"}
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    response = await async_client.get(
        f"/api/v1/documents/{str(doc_id_obj)}",
        headers=user_token_headers
    )
    assert response.status_code == 404
    assert "não encontrado" in response.json()["detail"]

async def test_update_document(async_client: AsyncClient, db_session: AsyncSession, user_token_headers: Dict[str, str], test_user: User) -> None:
    """Testa a atualização de um documento."""
    doc_id_obj = uuid.uuid4()
    doc = Document(
        id=doc_id_obj,
        user_id=test_user.id,
        type="comprovante_residencia",
        content_json={"endereco": "Rua Antiga, 123"}
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    response = await async_client.put(
        f"/api/v1/documents/{str(doc_id_obj)}",
        headers=user_token_headers,
        json={
            "type": "comprovante_residencia",
            "content_json": {"endereco": "Rua Nova, 456"}
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(doc_id_obj)
    assert data["type"] == "comprovante_residencia"
    assert data["content_json"]["endereco"] == "Rua Nova, 456"

async def test_delete_document(async_client: AsyncClient, db_session: AsyncSession, user_token_headers: Dict[str, str], test_user: User) -> None:
    """Testa a exclusão de um documento."""
    doc_id_obj = uuid.uuid4()
    doc = Document(
        id=doc_id_obj,
        user_id=test_user.id,
        type="cartao_vacina",
        content_json={"vacinas": ["Covid-19", "Influenza"]}
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    response = await async_client.delete(
        f"/api/v1/documents/{str(doc_id_obj)}",
        headers=user_token_headers
    )
    assert response.status_code == 204
    result = await db_session.execute(select(Document).where(Document.id == doc_id_obj))
    assert result.scalar_one_or_none() is None
    
    get_response = await async_client.get(
        f"/api/v1/documents/{str(doc_id_obj)}",
        headers=user_token_headers
    )
    assert get_response.status_code == 404

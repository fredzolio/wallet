from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import uuid

from app.core.deps import get_current_user
from app.db.session import get_db
from app.api.v1.deps import limiter
from app.models.document import Document
from app.models.user import User
from app.schemas.document import DocumentCreate, DocumentResponse, DocumentsList

router = APIRouter(prefix="/documents")

@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def create_document(
    request: Request,
    document_in: DocumentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Cria um novo documento digital para o usuário atual.
    """
    # Criar o documento
    document = Document(
        user_id=current_user.id,
        type=document_in.type,
        content_json=document_in.content_json
    )
    
    db.add(document)
    await db.commit()
    await db.refresh(document)
    
    return document

@router.get("", response_model=DocumentsList)
async def list_documents(
    skip: int = 0,
    limit: int = 100,
    type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Lista os documentos do usuário atual, com filtragem opcional por tipo.
    """
    # Construir query
    query = select(Document).where(Document.user_id == current_user.id)
    
    # Filtrar por tipo se especificado
    if type:
        query = query.where(Document.type == type)
    
    # Paginação
    query = query.offset(skip).limit(limit)
    
    # Executar query
    result = await db.execute(query)
    documents = result.scalars().all()
    
    # Contar total
    count_query = select(func.count(Document.id)).where(Document.user_id == current_user.id)
    if type:
        count_query = count_query.where(Document.type == type)
    
    count_result = await db.execute(count_query)
    total = count_result.scalar()
    
    return DocumentsList(
        items=documents,
        total=total
    )

@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Obtém um documento específico pelo ID.
    """
    # Buscar documento
    document = await db.get(Document, document_id)
    
    # Verificar se documento existe e pertence ao usuário
    if not document or document.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento não encontrado"
        )
    
    return document

@router.put("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: uuid.UUID,
    document_in: DocumentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Atualiza um documento existente.
    """
    # Buscar documento
    document = await db.get(Document, document_id)
    
    # Verificar se documento existe e pertence ao usuário
    if not document or document.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento não encontrado"
        )
    
    # Atualizar campos
    document.type = document_in.type
    document.content_json = document_in.content_json
    
    await db.commit()
    await db.refresh(document)
    
    return document

@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Remove um documento.
    """
    # Buscar documento
    document = await db.get(Document, document_id)
    
    # Verificar se documento existe e pertence ao usuário
    if not document or document.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento não encontrado"
        )
    
    # Remover documento
    await db.delete(document)
    await db.commit()
    
    return None

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from typing import Dict, Any

from app.api.v1.deps import redis, limiter
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.repository import (
    RepositoryQueryRequest, 
    RepositoryQueryResponse,
    RepositoryIndexRequest,
    RepositoryIndexResponse
)
from app.services.repository_knowledge import repository_knowledge

router = APIRouter(prefix="/repository")

@router.post("/index", response_model=RepositoryIndexResponse)
@limiter.limit("5/hour")
async def index_repository(
    request: Request,
    index_data: RepositoryIndexRequest = None,
    current_user: User = Depends(get_current_user)
):
    """
    Indexa o repositório para permitir consultas semânticas sobre o código.
    Esta operação pode levar algum tempo para repositórios grandes.
    """        
    try:
        result = await repository_knowledge.index_repository(
            ignore_patterns=index_data.ignore_patterns
        )
        
        return RepositoryIndexResponse(
            indexed_files=result["indexed_files"],
            total_files=result["total_files"],
            time_taken=result["time_taken"]
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao indexar repositório: {str(e)}"
        )

@router.post("/ask", response_model=RepositoryQueryResponse)
@limiter.limit("20/minute")
async def query_repository(
    request: Request,
    query: RepositoryQueryRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Responde a perguntas sobre o código-fonte do repositório.
    Utiliza o Google Generative AI com RAG para fornecer respostas contextualizadas.
    """
    try:
        # Verificar se o repositório foi indexado
        indexed_files = await redis.scard("repo:indexed_files")
        
        if not indexed_files:
            return RepositoryQueryResponse(
                answer="O repositório ainda não foi indexado. Por favor, execute a indexação primeiro.",
                contexts=[]
            )
            
        # Buscar resposta para a pergunta
        result = await repository_knowledge.answer_code_question(query.question)
        
        # Formatar a resposta
        return RepositoryQueryResponse(
            answer=result["answer"],
            contexts=result["contexts"]
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao processar consulta: {str(e)}"
        )

@router.get("/status")
@limiter.limit("60/minute")
async def repository_status(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Obtém o status da indexação do repositório.
    """
    try:
        # Verificar metadados da indexação
        metadata_json = await redis.get("repo:index:metadata")
        indexed_files = await redis.scard("repo:indexed_files")
        
        if not metadata_json:
            return {
                "indexed": False,
                "indexed_files": 0,
                "last_update": None
            }
            
        import json
        metadata = json.loads(metadata_json)
        
        return {
            "indexed": indexed_files > 0,
            "indexed_files": indexed_files,
            "last_update": metadata.get("last_update"),
            "total_files": metadata.get("total_files")
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao obter status do repositório: {str(e)}"
        ) 
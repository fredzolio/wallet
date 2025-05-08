from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any

class RepositoryQueryRequest(BaseModel):
    """Schema para consulta ao repositório."""
    question: str = Field(..., description="Pergunta sobre o código do repositório")

class RepositoryIndexRequest(BaseModel):
    """Schema para requisição de indexação do repositório."""
    ignore_patterns: Optional[List[str]] = Field(
        [
                ".git/", ".venv/", "__pycache__/", "*.pyc", "*.pyo", 
                "node_modules/", ".pytest_cache/", "*.lock", "*.so",
                ".*", ".*/", "alembic/", "__init__.py"
            ], 
        description="Padrões de arquivos/diretórios a ignorar durante a indexação"
    )

class CodeContext(BaseModel):
    """Schema para contexto de código retornado."""
    file_path: str
    line_start: int
    line_end: int
    snippet: str

class RepositoryQueryResponse(BaseModel):
    """Schema para resposta a consultas sobre o repositório."""
    answer: str
    contexts: List[CodeContext] = []

class RepositoryIndexResponse(BaseModel):
    """Schema para resposta de indexação do repositório."""
    indexed_files: int
    total_files: int
    time_taken: float 
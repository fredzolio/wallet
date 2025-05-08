import uuid
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict, Any, List

class DocumentBase(BaseModel):
    """Schema base para documentos."""
    type: str = Field(..., description="Tipo do documento (CPF, RG, comprovante_vacinacao, etc.)")
    content_json: Dict[str, Any] = Field(..., description="Conteúdo do documento em formato JSON")

class DocumentCreate(DocumentBase):
    """Schema para criação de documento."""
    pass

class DocumentResponse(DocumentBase):
    """Schema para resposta com dados do documento."""
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True

class DocumentsList(BaseModel):
    """Schema para listar múltiplos documentos."""
    items: List[DocumentResponse]
    total: int

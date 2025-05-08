from pydantic import BaseModel, Field
from typing import Optional, Dict, List

class ChatbotRequest(BaseModel):
    """Schema para requisição ao chatbot."""
    question: str = Field(..., description="Pergunta do usuário para o chatbot")
    context: Optional[Dict[str, str]] = Field(None, description="Contexto opcional para a pergunta")

class ChatbotResponse(BaseModel):
    """Schema para resposta do chatbot."""
    answer: str
    confidence: float = Field(..., ge=0.0, le=1.0, description="Nível de confiança da resposta")
    question_id: str = Field(..., description="ID único para referência da pergunta")
    suggested_questions: Optional[list[str]] = None

class FeedbackRequest(BaseModel):
    """Schema para feedback de resposta do chatbot."""
    question_id: str = Field(..., description="ID da pergunta")
    is_helpful: bool = Field(..., description="Se a resposta foi útil")
    comment: Optional[str] = Field(None, description="Comentário adicional sobre a resposta")

class KnowledgeDocumentRequest(BaseModel):
    """Schema para adição de documento à base de conhecimento."""
    title: str = Field(..., description="Título do documento", min_length=3)
    content: str = Field(..., description="Conteúdo do documento", min_length=10)
    category: str = Field(..., description="Categoria do documento", min_length=2)

class KnowledgeDocumentResponse(BaseModel):
    """Schema para resposta de documento adicionado."""
    id: str
    title: str
    category: str
    chunks_count: int 
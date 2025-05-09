from pydantic import BaseModel, Field
from typing import Optional, Dict

class ChatbotRequest(BaseModel):
    """Schema para requisição ao chatbot."""
    question: str = Field(..., description="Pergunta do usuário para o chatbot")

class ChatbotResponse(BaseModel):
    """Schema para resposta do chatbot."""
    answer: str
    confidence: float = Field(..., ge=0.0, le=1.0, description="Nível de confiança da resposta")
    question_id: str = Field(..., description="ID único para referência da pergunta")
    suggested_questions: Optional[list[str]] = None
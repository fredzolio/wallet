from fastapi import APIRouter, Depends, Request
from typing import List
from uuid import uuid4

from app.api.v1.deps import limiter
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.chatbot import ChatbotRequest, ChatbotResponse
from app.services.llm_service import gemini_client

router = APIRouter(prefix="/chatbot")

def get_suggested_questions() -> List[str]:
    """
    Retorna perguntas sugeridas para o usuário.
    """
    return [
        "Qual o horário de atendimento da prefeitura?",
        "Qual o endereço da prefeitura?",
        "Como pagar meu IPTU?"
    ]

@router.post("/ask", response_model=ChatbotResponse)
@limiter.limit("30/minute")
async def ask_chatbot(
    request: Request,
    question_data: ChatbotRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Responde a perguntas sobre a Prefeitura do Rio de Janeiro 
    usando o modelo de linguagem Gemini.
    """
    # Gerar ID único para a pergunta
    question_id = str(uuid4())
    
    try:
        # Configurar o prompt do sistema para o contexto da Prefeitura
        system_prompt = """Você é um assistente oficial da Prefeitura do Rio de Janeiro.
        Responda de forma clara, objetiva e educada às perguntas sobre serviços,
        informações e procedimentos municipais. 
        Se você não souber a resposta específica, forneça informações gerais
        sobre como o cidadão pode encontrar a informação que procura."""
        
        # Obter resposta do Gemini
        answer = await gemini_client.generate_response(
            prompt=question_data.question,
            system_message=system_prompt
        )
        
        # Confiança padrão para as respostas do Gemini
        confidence = 0.8
        
        # Obter sugestões para próximas perguntas
        suggested_questions = get_suggested_questions()
        
        return ChatbotResponse(
            answer=answer,
            confidence=confidence,
            question_id=question_id,
            suggested_questions=suggested_questions
        )
    except Exception:
        # Em caso de erro, retornar mensagem de fallback
        return ChatbotResponse(
            answer="Desculpe, estou com dificuldades técnicas no momento. Tente novamente mais tarde.",
            confidence=0.1,
            question_id=question_id,
            suggested_questions=get_suggested_questions()
        )

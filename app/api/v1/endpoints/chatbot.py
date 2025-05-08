from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Body, Request
from uuid import uuid4, UUID
import re
from typing import Dict, List, Optional, Any
import json
import time

from app.api.v1.deps import redis, limiter, increment_counter
from app.core.deps import get_current_user
from app.models.user import User
from app.core.config import settings
from app.schemas.chatbot import ChatbotRequest, ChatbotResponse, FeedbackRequest, KnowledgeDocumentRequest
from app.services.llm_service import gemini_client
from app.services.knowledge_base import knowledge_base

router = APIRouter(prefix="/chatbot")

# Serializador JSON personalizado para lidar com UUIDs
class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, UUID):
            # Converter UUID para string
            return str(obj)
        return super().default(obj)

# Mapeamento de palavras-chave para respostas pré-definidas (fallback)
CHATBOT_RESPONSES: Dict[str, Dict[str, str | float]] = {
    "horario_atendimento": {
        "answer": settings.CHATBOT_DEFAULT_RESPONSES["horario_atendimento"],
        "confidence": 0.95
    },
    "endereco_prefeitura": {
        "answer": settings.CHATBOT_DEFAULT_RESPONSES["endereco_prefeitura"],
        "confidence": 0.95
    },
    "onde_pagar_iptu": {
        "answer": settings.CHATBOT_DEFAULT_RESPONSES["onde_pagar_iptu"],
        "confidence": 0.95
    },
    "fallback": {
        "answer": "Desculpe, não entendi sua pergunta. Poderia reformular?",
        "confidence": 0.3
    }
}

# Mapeamento de frases de entrada para palavras-chave
INTENT_PATTERNS = {
    r"(?i)hor[aá]rio.*atendimento|(?i)quando.*(?:aberto|funciona)|(?i)que\shoras?": "horario_atendimento",
    r"(?i)endere[çc]o.*prefeitura|(?i)onde.*prefeitura|(?i)local.*prefeitura": "endereco_prefeitura",
    r"(?i)onde.*pagar.*iptu|(?i)como.*pagar.*iptu|(?i)pagamento.*iptu": "onde_pagar_iptu"
}

def detect_intent(question: str) -> str:
    """
    Detecta a intenção da pergunta do usuário através
    de expressões regulares simples.
    """
    for pattern, intent in INTENT_PATTERNS.items():
        if re.search(pattern, question):
            return intent
    
    return "fallback"

def get_suggested_questions(intent: str) -> List[str]:
    """
    Retorna perguntas sugeridas com base na intenção detectada.
    """
    suggestions_map = {
        "horario_atendimento": [
            "Qual o endereço da prefeitura?",
            "Como pagar meu IPTU?"
        ],
        "endereco_prefeitura": [
            "Qual o horário de atendimento?",
            "Como pagar meu IPTU?"
        ],
        "onde_pagar_iptu": [
            "Qual o horário de atendimento?",
            "Qual o endereço da prefeitura?"
        ],
        "fallback": [
            "Qual o horário de atendimento?",
            "Qual o endereço da prefeitura?",
            "Como pagar meu IPTU?"
        ]
    }
    
    return suggestions_map.get(intent, suggestions_map["fallback"])

async def store_conversation(user_id: int, question: str, answer: str, question_id: str):
    """
    Armazena a conversa no Redis para análise futura.
    """
    await increment_counter(f"chatbot:questions_count:{user_id}")
    
    conversation_data = {
        "user_id": user_id,
        "question": question,
        "answer": answer,
        "timestamp": str(int(time.time())),
        "question_id": question_id
    }
    
    # Armazenar a conversa usando o serializador personalizado
    await redis.lpush(
        f"chatbot:conversations:{user_id}", 
        json.dumps(conversation_data, cls=UUIDEncoder)
    )
    
    # Limitar a 50 conversas por usuário
    await redis.ltrim(f"chatbot:conversations:{user_id}", 0, 49)

@router.post("/ask", response_model=ChatbotResponse)
@limiter.limit("30/minute")
async def ask_chatbot(
    request: Request,
    question_data: ChatbotRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """
    Responde a perguntas usando o modelo LLM.
    Se configurado, usa RAG para responder com base na base de conhecimento.
    """
    # Gerar ID único para a pergunta
    question_id = str(uuid4())
    
    try:
        # Se LLM está habilitado
        if settings.USE_LLM:
            # Buscar contextos relevantes da base de conhecimento
            context_docs = []
            search_results = await knowledge_base.search(question_data.question)
            
            if search_results:
                context_docs = [result["text"] for result in search_results]
                
                # Responder usando RAG
                system_prompt = "Você é um assistente oficial da Prefeitura. Responda de forma clara, objetiva e educada."
                answer = await gemini_client.rag_response(question_data.question, context_docs, system_prompt)
                confidence = 0.8  # Confiança alta para respostas do LLM com contexto
            else:
                # Responder apenas com o LLM
                system_prompt = """Você é um assistente oficial da Prefeitura do Rio de Janeiro.
                Responda de forma clara, objetiva e educada. 
                Se você não souber a resposta, diga 'Não tenho essa informação no momento.'"""
                
                answer = await gemini_client.generate_response(
                    prompt=question_data.question,
                    system_message=system_prompt
                )
                confidence = 0.6  # Confiança média para respostas do LLM sem contexto
        else:
            # Usar o sistema baseado em regras como fallback
            intent = detect_intent(question_data.question)
            response_data = CHATBOT_RESPONSES.get(intent, CHATBOT_RESPONSES["fallback"])
            answer = response_data["answer"]
            confidence = response_data["confidence"]
        
        # Armazenar conversa em background
        background_tasks.add_task(
            store_conversation,
            current_user.id,
            question_data.question,
            answer,
            question_id
        )
        
        # Obter sugestões para a próxima pergunta
        suggested_questions = get_suggested_questions(
            detect_intent(question_data.question)
        )
        
        return ChatbotResponse(
            answer=answer,
            confidence=confidence,
            question_id=question_id,
            suggested_questions=suggested_questions
        )
    except Exception as e:
        # Em caso de erro, retornar mensagem de fallback
        return ChatbotResponse(
            answer="Desculpe, estou com dificuldades técnicas no momento. Tente novamente mais tarde.",
            confidence=0.1,
            question_id=question_id,
            suggested_questions=get_suggested_questions("fallback")
        )

@router.post("/feedback", status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")
async def submit_feedback(
    request: Request,
    feedback: FeedbackRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Recebe feedback do usuário sobre uma resposta.
    Útil para melhorar o sistema de chatbot.
    """
    try:
        # Armazenar feedback no Redis
        feedback_data = {
            "user_id": current_user.id,
            "question_id": feedback.question_id,
            "is_helpful": feedback.is_helpful,
            "comment": feedback.comment,
            "timestamp": str(int(time.time()))
        }
        
        await redis.set(
            f"chatbot:feedback:{feedback.question_id}",
            json.dumps(feedback_data),
            ex=60*60*24*30  # Expirar em 30 dias
        )
        
        return {"message": "Feedback recebido com sucesso. Obrigado!"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao processar feedback"
        )

@router.post("/knowledge", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def add_knowledge(
    request: Request,
    document: KnowledgeDocumentRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Adiciona um documento à base de conhecimento do chatbot.
    """
    try:
        doc_id = await knowledge_base.add_document(
            title=document.title,
            content=document.content,
            category=document.category
        )
        
        return {
            "message": "Documento adicionado à base de conhecimento",
            "document_id": doc_id
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao adicionar documento: {str(e)}"
        )

@router.get("/knowledge/{category}")
@limiter.limit("20/minute")
async def get_knowledge_documents(
    request: Request,
    category: str,
    current_user: User = Depends(get_current_user)
):
    """
    Obtém documentos da base de conhecimento por categoria.
    """
    try:
        documents = await knowledge_base.get_documents_by_category(category)
        
        return {
            "category": category,
            "count": len(documents),
            "documents": documents
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao buscar documentos: {str(e)}"
        )

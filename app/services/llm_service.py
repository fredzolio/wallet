from typing import List
import logging
from app.core.config import settings
import random
from google import genai
import asyncio
from google.genai.errors import ClientError

logger = logging.getLogger(__name__)

# Respostas padrão para fallback quando o LLM falhar
FALLBACK_RESPONSES = {
    "geral": [
        "Olá! Sou o assistente da Prefeitura. Como posso ajudar?",
        "Posso fornecer informações sobre serviços da Prefeitura. Em que posso ajudar?",
        "Estou aqui para responder suas dúvidas sobre a cidade. Como posso ajudar?",
    ],
    "horario": [
        "O atendimento da prefeitura é de segunda a sexta, das 8h às 17h.",
        "Nosso horário de funcionamento é das 8h às 17h em dias úteis.",
    ],
    "endereco": [
        "O endereço da prefeitura é Rua Afonso Cavalcanti, 455 - Cidade Nova.",
        "Estamos localizados na Rua Afonso Cavalcanti, 455 - Cidade Nova, Rio de Janeiro.",
    ],
    "iptu": [
        "O IPTU pode ser pago em qualquer agência bancária ou casa lotérica até a data de vencimento.",
        "Para pagar o IPTU, utilize o boleto em qualquer banco ou casa lotérica.",
    ]
}

async def retry_with_backoff(func, *args, max_retries=5, initial_delay=1, **kwargs):
    """
    Executa uma função com retry e backoff exponencial.
    
    Args:
        func: Função a ser executada
        *args: Argumentos para a função
        max_retries: Número máximo de tentativas
        initial_delay: Delay inicial em segundos
        **kwargs: Argumentos nomeados para a função
        
    Returns:
        Resultado da função
    """
    delay = initial_delay
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except ClientError as e:
            last_exception = e
            # Se for erro de rate limit (429)
            if hasattr(e, 'status_code') and e.status_code == 429:
                logger.warning(f"Rate limit atingido (tentativa {attempt+1}/{max_retries}). Aguardando {delay}s...")
                await asyncio.sleep(delay)
                # Backoff exponencial
                delay *= 2
            else:
                # Se não for rate limit, levanta a exceção
                raise
    
    # Se chegou aqui, todas as tentativas falharam
    logger.error(f"Todas as {max_retries} tentativas falharam. Último erro: {str(last_exception)}")
    raise last_exception

class GeminiClient:
    """Cliente para integração com o Google Generative AI (Gemini)."""
    
    def __init__(self):
        """Inicializa o cliente com a API key do Google Generative AI."""
        self.api_key = settings.GOOGLE_GENAI_API_KEY
        self.model_name = settings.GOOGLE_GENAI_MODEL
        
        # Inicializa o cliente Gemini se a API key estiver configurada
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None
        
    def _get_fallback_response(self, query: str) -> str:
        """
        Retorna uma resposta de fallback baseada em palavras-chave na consulta.
        
        Args:
            query: Consulta do usuário
            
        Returns:
            Resposta pré-definida
        """
        query_lower = query.lower()
        
        if any(word in query_lower for word in ["horário", "horario", "funcionamento", "expediente"]):
            category = "horario"
        elif any(word in query_lower for word in ["endereço", "endereco", "localização", "onde fica"]):
            category = "endereco"
        elif any(word in query_lower for word in ["iptu", "imposto", "pagar", "pagamento"]):
            category = "iptu"
        else:
            category = "geral"
            
        responses = FALLBACK_RESPONSES.get(category, FALLBACK_RESPONSES["geral"])
        return random.choice(responses)
    
    async def _check_api_connectivity(self) -> bool:
        """
        Verifica se consegue conectar-se à API do Google Generative AI.
        
        Returns:
            True se a API estiver disponível, False caso contrário
        """
        if not self.client:
            logger.error("API key do Google Generative AI não configurada")
            return False
        
        try:
            # Tentar listar modelos disponíveis para verificar conectividade
            models = self.client.list_models()
            return any(model.name.startswith("models/gemini") for model in models)
        except Exception as e:
            logger.exception(f"Erro ao conectar com a API do Google Generative AI: {str(e)}")
            return False
    
    async def _generate_response_internal(self, prompt: str, system_message: str = "", temperature: float = 0.7, max_tokens: int = 500) -> str:
        """
        Função interna para gerar resposta, sem mecanismo de retry.
        """
        # Verificar se a API está configurada e disponível
        if not self.client:
            logger.error("API key do Google Generative AI não configurada")
            return self._get_fallback_response(prompt)
        
        # Log adicional
        logger.info(f"Gerando resposta com modelo: {self.model_name}")
        logger.info(f"Tamanho do prompt: {len(prompt)} caracteres")
        
        # Configurar o modelo
        config = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
            "top_p": 0.95,
            "top_k": 64
        }
        
        # Para prompts longos, simplificar
        simplified_prompt = prompt
        if len(prompt) > 1000:
            logger.info("Prompt muito longo, simplificando...")
            simplified_prompt = prompt[:1000]
        
        # Preparar o conteúdo com a mensagem de sistema
        contents = []
        if system_message:
            contents.append({"role": "user", "parts": [{"text": system_message}]})
        
        contents.append({"role": "user", "parts": [{"text": simplified_prompt}]})
        
        # Configurar geração de conteúdo
        response = self.client.models.generate_content(
            model=self.model_name, 
            contents=contents,
            config=config,
        )
        
        # Processar resposta
        output_text = ""
        if hasattr(response, "candidates") and response.candidates:
            for candidate in response.candidates:
                if (
                    hasattr(candidate, "content")
                    and candidate.content
                    and hasattr(candidate.content, "parts")
                ):
                    for part in candidate.content.parts:
                        if hasattr(part, "text") and part.text:
                            output_text += part.text
        
        # Se a resposta for vazia ou muito curta, usar fallback
        if not output_text or len(output_text) < 5:
            logger.warning("Resposta vazia ou muito curta, usando fallback")
            return self._get_fallback_response(prompt)
            
        logger.info(f"Resposta gerada com comprimento: {len(output_text)} caracteres")
        return output_text
    
    async def generate_response(self, prompt: str, system_message: str = "", temperature: float = 0.7, max_tokens: int = 500) -> str:
        """
        Gera uma resposta utilizando o modelo Gemini do Google Generative AI.
        Com mecanismo de retry para erros de rate limit.
        
        Args:
            prompt: Texto de entrada para o modelo
            system_message: Mensagem de sistema para configurar o comportamento
            temperature: Temperatura para geração (criatividade)
            max_tokens: Número máximo de tokens a gerar
            
        Returns:
            Texto de resposta gerado
        """
        try:
            return await retry_with_backoff(
                self._generate_response_internal,
                prompt=prompt,
                system_message=system_message,
                temperature=temperature,
                max_tokens=max_tokens
            )
        except Exception as e:
            logger.exception(f"Erro ao gerar resposta do LLM: {str(e)}")
            return self._get_fallback_response(prompt)

    async def _embed_text_internal(self, text: str) -> List[float]:
        """
        Função interna para gerar embeddings, sem mecanismo de retry.
        """
        # Verificar se a API está configurada e disponível
        if not self.client:
            logger.error("API key do Google Generative AI não configurada")
            return []
        
        # Simplificar texto muito longo para embeddings
        simplified_text = text
        if len(text) > 1000:
            logger.info(f"Texto para embedding muito longo ({len(text)} caracteres), reduzindo...")
            simplified_text = text[:1000]
        
        # Usar modelo de embedding do Google Generative AI
        embedding_model = "models/embedding-001"
        result = self.client.models.embed_content(
            model=embedding_model,
            contents=[simplified_text],
        )
        
        # Extrair os valores float do objeto ContentEmbedding
        if hasattr(result, 'embeddings') and result.embeddings:
            # Verificar se embeddings é um objeto ContentEmbedding ou já uma lista
            if hasattr(result.embeddings[0], 'values'):
                return result.embeddings[0].values
            else:
                return list(map(float, result.embeddings[0]))
        
        logger.error("Falha ao extrair embeddings do resultado")
        return []
    
    async def embed_text(self, text: str) -> List[float]:
        """
        Gera embeddings para o texto usando o modelo.
        Útil para buscas semânticas.
        Com mecanismo de retry para erros de rate limit.
        
        Args:
            text: Texto para gerar embeddings
            
        Returns:
            Lista de valores float representando o embedding
        """
        try:
            return await retry_with_backoff(self._embed_text_internal, text)
        except Exception as e:
            logger.exception(f"Erro ao gerar embeddings: {str(e)}")
            return []
            
    async def rag_response(self, query: str, context_docs: List[str], system_prompt: str = "") -> str:
        """
        Gera uma resposta baseada em RAG (Retrieval Augmented Generation).
        Utiliza documentos de contexto para enriquecer a resposta.
        
        Args:
            query: Pergunta do usuário
            context_docs: Lista de documentos de contexto
            system_prompt: Prompt de sistema para configurar o comportamento
            
        Returns:
            Resposta gerada pelo modelo
        """
        # Log para debugging
        logger.info(f"Gerando resposta RAG para query: {query[:100]}...")
        logger.info(f"Número de documentos de contexto: {len(context_docs)}")
        
        # Se não conseguir obter um modelo, usar fallback
        if not self.client:
            return self._get_fallback_response(query)
            
        # Para prompts longos, simplificar
        if len(context_docs) > 3:
            logger.info("Reduzindo número de documentos de contexto")
            # Usar apenas os 3 documentos mais relevantes
            context_docs = context_docs[:3]
        
        # Unir documentos de contexto
        context = "\n\n".join(context_docs)
        
        # Limitar tamanho do contexto
        if len(context) > 1500:
            logger.info(f"Contexto muito grande ({len(context)} caracteres), reduzindo...")
            context = context[:1500] + "..."
        
        # Construir prompt RAG
        rag_prompt = f"""Contexto: {context}

Pergunta: {query}

Responda utilizando as informações do contexto. Seja claro e objetivo."""
        
        # Gerar resposta
        response = await self.generate_response(rag_prompt, system_message=system_prompt or "Você é um assistente oficial da Prefeitura. Seja claro e objetivo.")
        
        # Se a resposta parece ser inválida ou muito genérica, usar fallback
        if not response or len(response) < 10 or "desculpe" in response.lower():
            logger.warning("Resposta LLM inadequada ou genérica, usando fallback")
            return self._get_fallback_response(query)
            
        return response

# Instância global para uso em toda a aplicação
gemini_client = GeminiClient() 
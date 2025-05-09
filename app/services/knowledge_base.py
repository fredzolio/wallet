import json
import os
from typing import List, Dict, Any
import logging
from pathlib import Path
import numpy as np
import aiofiles
import pickle
import time

from app.api.v1.deps import redis
from app.services.llm_service import gemini_client

logger = logging.getLogger(__name__)

class KnowledgeBase:
    """
    Gerencia a base de conhecimento para o chatbot.
    Armazena e recupera documentos, gerencia embeddings e realiza buscas semânticas.
    """
    
    def __init__(self):
        """Inicializa a base de conhecimento."""
        self.redis = redis
        self.knowledge_dir = Path("app/data/knowledge")
        self.embeddings_dir = Path("app/data/embeddings")
        
        # Criar diretórios se não existirem
        os.makedirs(self.knowledge_dir, exist_ok=True)
        os.makedirs(self.embeddings_dir, exist_ok=True)
        
    async def add_document(self, title: str, content: str, category: str) -> str:
        """
        Adiciona um documento à base de conhecimento.
        
        Args:
            title: Título do documento
            content: Conteúdo do documento
            category: Categoria do documento (ex: 'iptu', 'atendimento')
            
        Returns:
            ID do documento adicionado
        """
        # Gerar ID único para o documento
        doc_id = f"{category}_{int(time.time())}"
        
        # Dividir o conteúdo em chunks para melhor indexação
        chunks = self._split_into_chunks(content, max_chunk_size=512)
        
        # Criar metadados do documento
        document_data = {
            "id": doc_id,
            "title": title,
            "category": category,
            "content": content,
            "chunks": chunks,
            "created_at": time.time()
        }
        
        # Salvar documento JSON
        async with aiofiles.open(
            self.knowledge_dir / f"{doc_id}.json", "w", encoding="utf-8"
        ) as f:
            await f.write(json.dumps(document_data, ensure_ascii=False))
            
        # Gerar embeddings para cada chunk
        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}_chunk_{i}"
            
            # Obter embedding do chunk usando o serviço LLM
            embedding = await gemini_client.embed_text(chunk)
            
            if embedding:
                # Salvar embedding para cada chunk
                np_embedding = np.array(embedding, dtype=np.float32)
                
                with open(self.embeddings_dir / f"{chunk_id}.pickle", "wb") as f:
                    pickle.dump(np_embedding, f)
                
                # Armazenar metadados no Redis
                await self.redis.set(
                    f"knowledge:chunk:{chunk_id}",
                    json.dumps({
                        "document_id": doc_id,
                        "document_title": title,
                        "document_category": category,
                        "text": chunk,
                        "position": i
                    })
                )
                
        # Indexar o documento por categoria para busca rápida
        await self.redis.sadd(f"knowledge:category:{category}", doc_id)
        
        return doc_id
    
    def _split_into_chunks(self, text: str, max_chunk_size: int = 512) -> List[str]:
        """
        Divide o texto em chunks para processamento.
        
        Args:
            text: Texto a ser dividido
            max_chunk_size: Tamanho máximo de cada chunk em caracteres
            
        Returns:
            Lista de chunks de texto
        """
        # Dividir por parágrafos primeiro
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        
        chunks = []
        current_chunk = ""
        
        for paragraph in paragraphs:
            # Se o parágrafo for maior que o tamanho máximo, dividir em sentenças
            if len(paragraph) > max_chunk_size:
                sentences = [s.strip() + "." for s in paragraph.split(".") if s.strip()]
                for sentence in sentences:
                    if len(current_chunk) + len(sentence) + 1 <= max_chunk_size:
                        if current_chunk:
                            current_chunk += " " + sentence
                        else:
                            current_chunk = sentence
                    else:
                        chunks.append(current_chunk)
                        current_chunk = sentence
            else:
                # Se adicionar este parágrafo ultrapassa o tamanho máximo, 
                # iniciar novo chunk
                if len(current_chunk) + len(paragraph) + 1 > max_chunk_size:
                    chunks.append(current_chunk)
                    current_chunk = paragraph
                else:
                    if current_chunk:
                        current_chunk += " " + paragraph
                    else:
                        current_chunk = paragraph
        
        # Adicionar o último chunk se não estiver vazio
        if current_chunk:
            chunks.append(current_chunk)
            
        return chunks
    
    async def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Realiza busca semântica na base de conhecimento.
        
        Args:
            query: Texto da pergunta
            top_k: Número de resultados a retornar
            
        Returns:
            Lista de documentos relevantes para a query
        """
        # Obter embedding da query
        query_embedding = await gemini_client.embed_text(query)
        
        if not query_embedding:
            logger.warning("Não foi possível gerar embedding para a query")
            return []
            
        # Converter para numpy array
        query_embedding_np = np.array(query_embedding, dtype=np.float32)
        
        # Encontrar arquivos de embedding
        embedding_files = list(self.embeddings_dir.glob("*.pickle"))
        
        if not embedding_files:
            logger.warning("Nenhum embedding encontrado na base de conhecimento")
            return []
            
        # Calcular similaridade com cada documento
        similarities = []
        
        for emb_file in embedding_files:
            chunk_id = emb_file.stem
            
            try:
                with open(emb_file, "rb") as f:
                    chunk_embedding = pickle.load(f)
                
                # Calcular similaridade de cosseno
                similarity = self._cosine_similarity(query_embedding_np, chunk_embedding)
                
                # Obter metadados do chunk
                chunk_data_json = await self.redis.get(f"knowledge:chunk:{chunk_id}")
                
                if chunk_data_json:
                    chunk_data = json.loads(chunk_data_json)
                    similarities.append((similarity, chunk_data))
            except Exception as e:
                logger.error(f"Erro ao processar embedding {chunk_id}: {str(e)}")
                continue
        
        # Ordenar por similaridade (decrescente)
        similarities.sort(key=lambda x: x[0], reverse=True)
        
        # Retornar os top_k mais relevantes
        results = []
        seen_documents = set()
        
        for similarity, chunk_data in similarities[:top_k*2]:  # Pegar o dobro para garantir diversidade
            doc_id = chunk_data.get("document_id")
            
            # Evitar documentos duplicados
            if doc_id not in seen_documents:
                seen_documents.add(doc_id)
                
                results.append({
                    "text": chunk_data.get("text", ""),
                    "document_title": chunk_data.get("document_title", ""),
                    "document_id": doc_id,
                    "document_category": chunk_data.get("document_category", ""),
                    "relevance": float(similarity)
                })
                
                # Parar quando atingir top_k documentos únicos
                if len(results) >= top_k:
                    break
        
        return results
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """
        Calcula a similaridade de cosseno entre dois vetores.
        
        Args:
            a: Primeiro vetor
            b: Segundo vetor
            
        Returns:
            Similaridade de cosseno (entre -1 e 1)
        """
        # Normalizar os vetores
        a_norm = np.linalg.norm(a)
        b_norm = np.linalg.norm(b)
        
        # Evitar divisão por zero
        if a_norm == 0 or b_norm == 0:
            return 0.0
            
        # Calcular similaridade de cosseno
        return np.dot(a, b) / (a_norm * b_norm)
    
    async def get_documents_by_category(self, category: str) -> List[Dict[str, Any]]:
        """
        Obtém todos os documentos de uma categoria.
        
        Args:
            category: Categoria dos documentos a buscar
            
        Returns:
            Lista de documentos da categoria
        """
        # Obter IDs dos documentos da categoria
        doc_ids = await self.redis.smembers(f"knowledge:category:{category}")
        
        documents = []
        
        for doc_id in doc_ids:
            try:
                # Ler arquivo do documento
                doc_path = self.knowledge_dir / f"{doc_id}.json"
                
                if not doc_path.exists():
                    continue
                    
                async with aiofiles.open(doc_path, "r", encoding="utf-8") as f:
                    content = await f.read()
                    document = json.loads(content)
                    
                    # Adicionar apenas informações essenciais
                    documents.append({
                        "id": document.get("id"),
                        "title": document.get("title"),
                        "category": document.get("category"),
                        "created_at": document.get("created_at"),
                        "content_preview": document.get("content", "")[:150] + "..." 
                        if len(document.get("content", "")) > 150 else document.get("content", ""),
                        "chunks_count": len(document.get("chunks", []))
                    })
            except Exception as e:
                logger.error(f"Erro ao ler documento {doc_id}: {str(e)}")
                continue
        
        # Ordenar por data de criação (mais recentes primeiro)
        documents.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        
        return documents

# Instância global
knowledge_base = KnowledgeBase() 
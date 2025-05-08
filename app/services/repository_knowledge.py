import json
import os
from typing import List, Dict, Any, Optional
import logging
from pathlib import Path
import numpy as np
import aiofiles
import pickle
import time
import asyncio
import subprocess
from glob import glob

from app.core.config import settings
from app.api.v1.deps import redis
from app.services.llm_service import gemini_client

logger = logging.getLogger(__name__)

class RepositoryKnowledge:
    """
    Gerencia a base de conhecimento do repositório para consultas sobre o código.
    Indexa arquivos de código e permite consultas semânticas sobre a base de código.
    """
    
    def __init__(self):
        """Inicializa a base de conhecimento do repositório."""
        self.redis = redis
        self.repo_dir = Path(os.getcwd())
        self.code_embeddings_dir = Path("app/data/code_embeddings")
        
        # Criar diretórios se não existirem
        os.makedirs(self.code_embeddings_dir, exist_ok=True)
        
    async def index_repository(self, ignore_patterns: List[str] = [
                ".git/", ".venv/", "__pycache__/", "*.pyc", "*.pyo", 
                "node_modules/", ".pytest_cache/", "*.lock", "*.so",
                ".*", ".*/", "alembic/", "__init__.py"
            ]) -> Dict[str, Any]:
        """
        Indexa todo o repositório para busca semântica.
        
        Args:
            ignore_patterns: Padrões de arquivos/diretórios a ignorar
            
        Returns:
            Informações sobre o processo de indexação
        """   
        
        ignore_patterns =  [
            ".git/", ".venv/", "__pycache__/", "*.pyc", "*.pyo", 
            "node_modules/", ".pytest_cache/", "*.lock", "*.so",
            ".*", ".*/", "alembic/", "__init__.py"
        ]     
        # Contar arquivos indexados
        indexed_count = 0
        start_time = time.time()
        
        # Encontrar todos os arquivos de código
        code_files = []
        for root, dirs, files in os.walk(self.repo_dir):
            # Filtrar diretórios ignorados
            dirs[:] = [d for d in dirs if not any(
                d.startswith(p.strip("/")) for p in ignore_patterns if p.endswith("/")
            )]
            
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, self.repo_dir)
                
                # Ignorar arquivos conforme padrões
                if any(Path(rel_path).match(p) for p in ignore_patterns):
                    continue
                    
                # Filtrar apenas arquivos de texto/código
                if self._is_text_file(file_path):
                    code_files.append(rel_path)
        
        logger.info(f"Encontrados {len(code_files)} arquivos para indexar")
        
        # Indexar arquivos em paralelo (com limite para não sobrecarregar)
        tasks = []
        semaphore = asyncio.Semaphore(5)  # Limitar a 5 tarefas paralelas
        
        for file_path in code_files:
            task = asyncio.create_task(
                self._index_file(file_path, semaphore)
            )
            tasks.append(task)
            
        # Aguardar todas as tarefas terminarem
        results = await asyncio.gather(*tasks)
        indexed_count = sum(1 for r in results if r)
        
        # Salvar metadados da indexação
        await self.redis.set(
            "repo:index:metadata",
            json.dumps({
                "indexed_files": indexed_count,
                "total_files": len(code_files),
                "last_update": time.time(),
                "ignored_patterns": ignore_patterns
            })
        )
        
        return {
            "indexed_files": indexed_count,
            "total_files": len(code_files),
            "time_taken": time.time() - start_time
        }
        
    def _is_text_file(self, file_path: str) -> bool:
        """
        Verifica se um arquivo é um arquivo de texto/código.
        
        Args:
            file_path: Caminho do arquivo
            
        Returns:
            True se for um arquivo de texto, False caso contrário
        """
        # Extensões comuns de arquivos de código
        code_extensions = [
            '.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.css', '.scss',
            '.md', '.rst', '.json', '.yaml', '.yml', '.toml', '.ini',
            '.c', '.cpp', '.h', '.java', '.go', '.rs', '.php', '.rb'
        ]
        
        # Verificar extensão
        if any(file_path.endswith(ext) for ext in code_extensions):
            return True
            
        # Para outros arquivos, tentar verificar se é binário
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                f.read(1024)  # Tentar ler o início do arquivo
            return True
        except UnicodeDecodeError:
            return False
            
    async def _index_file(self, file_path: str, semaphore: asyncio.Semaphore) -> bool:
        """
        Indexa um arquivo de código.
        
        Args:
            file_path: Caminho relativo do arquivo
            semaphore: Semáforo para limitar concorrência
            
        Returns:
            True se o arquivo foi indexado com sucesso, False caso contrário
        """
        async with semaphore:
            try:
                abs_path = os.path.join(self.repo_dir, file_path)
                
                # Ler conteúdo do arquivo
                async with aiofiles.open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = await f.read()
                    
                # Dividir em segmentos para melhor processamento
                segments = self._split_code_into_segments(content, file_path)
                
                for i, segment in enumerate(segments):
                    segment_id = f"{file_path.replace('/', '_')}_seg_{i}"
                    
                    # Criar embedding para o segmento
                    embedding = await gemini_client.embed_text(segment["text"])
                    
                    if embedding:
                        # Salvar embedding
                        np_embedding = np.array(embedding, dtype=np.float32)
                        
                        with open(self.code_embeddings_dir / f"{segment_id}.pickle", "wb") as f:
                            pickle.dump(np_embedding, f)
                        
                        # Salvar metadados no Redis
                        await self.redis.set(
                            f"repo:segment:{segment_id}",
                            json.dumps({
                                "file_path": file_path,
                                "segment_number": i,
                                "line_start": segment["line_start"],
                                "line_end": segment["line_end"],
                                "text": segment["text"],
                            })
                        )
                
                # Adicionar à lista de arquivos indexados
                await self.redis.sadd("repo:indexed_files", file_path)
                
                return True
            except Exception as e:
                logger.error(f"Erro ao indexar arquivo {file_path}: {str(e)}")
                return False
                
    def _split_code_into_segments(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """
        Divide código em segmentos semânticos para melhor indexação.
        
        Args:
            content: Conteúdo do arquivo
            file_path: Caminho do arquivo
            
        Returns:
            Lista de segmentos com texto e metadados
        """
        lines = content.split('\n')
        segments = []
        
        # Tamanho máximo de linha por segmento
        max_lines = 100
        
        for i in range(0, len(lines), max_lines):
            segment_lines = lines[i:i+max_lines]
            segment_text = '\n'.join(segment_lines)
            
            # Ignorar segmentos vazios
            if not segment_text.strip():
                continue
                
            segments.append({
                "text": segment_text,
                "line_start": i + 1,  # Linhas começam em 1
                "line_end": min(i + len(segment_lines), len(lines)),
                "file_path": file_path
            })
            
        return segments
        
    async def search_repository(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Busca semanticamente no repositório.
        
        Args:
            query: Consulta de busca
            top_k: Número de resultados a retornar
            
        Returns:
            Lista de trechos de código relevantes
        """
        # Obter embedding da query
        query_embedding = await gemini_client.embed_text(query)
        
        if not query_embedding:
            logger.warning("Não foi possível gerar embedding para a query")
            return []
            
        # Converter para numpy array
        query_embedding_np = np.array(query_embedding, dtype=np.float32)
        
        # Encontrar arquivos de embedding
        embedding_files = list(self.code_embeddings_dir.glob("*.pickle"))
        
        if not embedding_files:
            logger.warning("Nenhum embedding encontrado na base de conhecimento")
            return []
            
        # Calcular similaridade com cada segmento
        similarities = []
        
        for emb_file in embedding_files:
            segment_id = emb_file.stem
            
            try:
                with open(emb_file, "rb") as f:
                    segment_embedding = pickle.load(f)
                
                # Calcular similaridade de cosseno
                similarity = self._cosine_similarity(query_embedding_np, segment_embedding)
                
                # Obter metadados do segmento
                segment_data_json = await self.redis.get(f"repo:segment:{segment_id}")
                
                if segment_data_json:
                    segment_data = json.loads(segment_data_json)
                    similarities.append((similarity, segment_data))
            except Exception as e:
                logger.error(f"Erro ao processar embedding {segment_id}: {str(e)}")
                continue
        
        # Ordenar por similaridade (decrescente)
        similarities.sort(key=lambda x: x[0], reverse=True)
        
        # Retornar os top_k mais relevantes
        results = []
        
        for similarity, segment_data in similarities[:top_k]:
            results.append({
                "file_path": segment_data.get("file_path", ""),
                "content": segment_data.get("text", ""),
                "line_start": segment_data.get("line_start", 0),
                "line_end": segment_data.get("line_end", 0),
                "relevance": float(similarity)
            })
        
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
        
    async def answer_code_question(self, query: str) -> Dict[str, Any]:
        """
        Responde a perguntas sobre o código do repositório.
        
        Args:
            query: Pergunta sobre o código
            
        Returns:
            Resposta com contextos relevantes
        """
        # Buscar trechos relevantes
        context_segments = await self.search_repository(query, top_k=3)
        
        if not context_segments:
            return {
                "answer": "Não encontrei informações relevantes sobre isso no repositório. Tente reformular a pergunta ou indexar o repositório primeiro.",
                "contexts": []
            }
            
        # Preparar contextos para o LLM
        contexts = []
        for segment in context_segments:
            file_path = segment["file_path"]
            content = segment["content"]
            line_info = f"Linhas {segment['line_start']}-{segment['line_end']}"
            
            contexts.append(f"Arquivo: {file_path} ({line_info})\n```\n{content}\n```")
            
        context_text = "\n\n".join(contexts)
        
        # Gerar prompt específico para código
        system_prompt = """Você é um assistente especializado em análise de código-fonte.
        Responda apenas usando as informações fornecidas nos trechos de código.
        Seja específico, técnico e preciso. Cite os arquivos e linhas relevantes em sua resposta.
        Se as informações não forem suficientes, diga isso claramente."""
        
        prompt = f"""Contexto do repositório:

{context_text}

Pergunta: {query}

Responda de forma concisa e específica, citando o arquivo relevante. Use apenas as informações presentes no contexto."""
        
        # Gerar resposta com o LLM
        answer = await gemini_client.generate_response(
            prompt=prompt,
            system_message=system_prompt,
            temperature=0.3,  # Baixa temperatura para respostas mais precisas
            max_tokens=800
        )
        
        return {
            "answer": answer,
            "contexts": [
                {
                    "file_path": seg["file_path"],
                    "line_start": seg["line_start"],
                    "line_end": seg["line_end"],
                    "snippet": seg["content"][:200] + "..." if len(seg["content"]) > 200 else seg["content"]
                }
                for seg in context_segments
            ]
        }

# Instância global para uso em toda a aplicação
repository_knowledge = RepositoryKnowledge() 
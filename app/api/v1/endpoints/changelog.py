from fastapi import APIRouter, Depends, status, HTTPException, BackgroundTasks
from typing import List, Dict, Optional
from pydantic import BaseModel
import os
import json

from app.core.deps import get_current_user
from app.models.user import User
from app.utils.git_analyzer import GitAnalyzer

router = APIRouter(prefix="/changelog")

class ChangelogEntry(BaseModel):
    """Modelo para uma entrada no changelog."""
    version: str
    date: str
    changes: List[str]
    deprecations: Optional[List[str]] = None
    breaking_changes: Optional[List[str]] = None

class ChangelogResponse(BaseModel):
    """Resposta da API de changelog."""
    entries: List[ChangelogEntry]
    latest_version: str
    api_version: str

# Inicializar o analisador Git
git_analyzer = GitAnalyzer()

# Caminho para o arquivo de versão
VERSION_FILE = "app/version.json"

async def update_version_info(force: bool = False):
    """
    Atualiza as informações de versão da API.
    Chamado em background ou quando solicitado.
    """
    # Verificar se é necessário atualizar (apenas a cada 12 horas, a menos que forçado)
    if os.path.exists(VERSION_FILE) and not force:
        try:
            with open(VERSION_FILE, "r") as f:
                version_info = json.load(f)
                
            # Se o arquivo foi atualizado há menos de 12 horas, não atualizar novamente
            import time
            file_mtime = os.path.getmtime(VERSION_FILE)
            if time.time() - file_mtime < 12 * 3600:
                return
        except:
            pass
    
    # Atualizar informações de versão
    git_analyzer.save_version_info(VERSION_FILE)
    
    # Gerar changelog se não existir
    if not os.path.exists("CHANGELOG.md"):
        git_analyzer.generate_changelog()

@router.get("", response_model=ChangelogResponse)
async def get_changelog(
    background_tasks: BackgroundTasks,
    force_update: bool = False,
    current_user: Optional[User] = Depends(get_current_user)
):
    """
    Retorna o histórico de mudanças da API.
    Útil para clientes acompanharem atualizações e migrações.
    
    Parâmetros:
    - force_update: Se True, força a atualização do changelog a partir do histórico Git
    """
    # Atualizar versão em background (ou imediatamente se forçado)
    if force_update:
        await update_version_info(True)
    else:
        background_tasks.add_task(update_version_info)
    
    # Obter versão atual da API
    try:
        api_version = "1.0.0"  # Versão padrão
        
        if os.path.exists(VERSION_FILE):
            with open(VERSION_FILE, "r") as f:
                version_info = json.load(f)
                api_version = version_info.get("version", "1.0.0")
    except Exception as e:
        api_version = "1.0.0"
    
    try:
        # Ler changelog markdown e converter para formato da API
        entries = []
        
        if os.path.exists("CHANGELOG.md"):
            with open("CHANGELOG.md", "r") as f:
                content = f.read()
                
            # Processar conteúdo do changelog
            sections = content.split("## ")
            
            for section in sections[1:]:  # Ignorar o cabeçalho
                lines = section.strip().split("\n")
                header = lines[0].strip()
                
                # Extrair versão e data
                import re
                match = re.match(r"([^\s]+)\s+\(([^)]+)\)", header)
                
                if match:
                    version = match.group(1)
                    date = match.group(2)
                    
                    # Processar categorias
                    changes = []
                    deprecations = []
                    breaking_changes = []
                    
                    current_category = None
                    
                    for line in lines[1:]:
                        if line.startswith("### "):
                            current_category = line[4:].strip()
                        elif line.startswith("* "):
                            item = line[2:].strip()
                            
                            if current_category == "BREAKING CHANGES":
                                breaking_changes.append(item)
                            elif current_category == "Deprecations":
                                deprecations.append(item)
                            elif current_category:
                                changes.append(f"{current_category}: {item}")
                    
                    # Criar entrada do changelog
                    entry = ChangelogEntry(
                        version=version,
                        date=date,
                        changes=changes,
                        deprecations=deprecations if deprecations else None,
                        breaking_changes=breaking_changes if breaking_changes else None
                    )
                    
                    entries.append(entry)
        
        # Se não houver entradas do changelog, usar as entradas padrão
        if not entries:
            entries = [
                ChangelogEntry(
                    version="1.0.0",
                    date="2024-06-01",
                    changes=[
                        "Versão inicial da API",
                        "Implementação de autenticação com JWT",
                        "Implementação de OAuth2 com Google",
                        "Autenticação de dois fatores (MFA)",
                        "Endpoints para documentos digitais",
                        "Endpoints para cartão de transporte",
                        "Simulação de chatbot"
                    ]
                )
            ]
        
        return ChangelogResponse(
            entries=entries,
            latest_version=entries[0].version if entries else "1.0.0",
            api_version=api_version
        )
    except Exception as e:
        # Fallback para versão estática em caso de erro
        entries = [
            ChangelogEntry(
                version="1.0.0",
                date="2024-06-01",
                changes=[
                    "Versão inicial da API",
                    "Implementação de autenticação com JWT",
                    "Implementação de OAuth2 com Google",
                    "Autenticação de dois fatores (MFA)",
                    "Endpoints para documentos digitais",
                    "Endpoints para cartão de transporte",
                    "Simulação de chatbot"
                ]
            )
        ]
        
        return ChangelogResponse(
            entries=entries,
            latest_version="1.0.0",
            api_version=api_version
        )

@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_changelog(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """
    Gera o changelog a partir do histórico Git.
    Executado em background para não bloquear a requisição.
    """
    try:
        background_tasks.add_task(git_analyzer.generate_changelog)
        background_tasks.add_task(git_analyzer.save_version_info, VERSION_FILE)
        
        return {
            "message": "Geração de changelog iniciada em background",
            "status": "processing"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao iniciar geração de changelog: {str(e)}"
        )

from fastapi import APIRouter, Depends, status, HTTPException
from typing import List, Dict, Optional
from pydantic import BaseModel
import os
import json
import logging
import subprocess

from app.core.deps import get_current_user
from app.models.user import User
from app.utils.git_analyzer import GitAnalyzer

logger = logging.getLogger(__name__)
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

# Caminhos para os arquivos
CHANGELOG_FILE = "CHANGELOG.md"
VERSION_FILE = "app/version.json"

# Inicializar o analisador Git como fallback
git_analyzer = GitAnalyzer()

def _get_api_version() -> str:
    """Obtém a versão atual da API."""
    try:
        if os.path.exists(VERSION_FILE):
            with open(VERSION_FILE, "r") as f:
                version_info = json.load(f)
                return version_info.get("version", "1.0.0")
        
        # Se não existir arquivo version.json, tentar obter da variável __version__
        import app
        return getattr(app, "__version__", "1.0.0")
    except Exception as e:
        logger.error(f"Erro ao obter versão da API: {str(e)}")
    
    return "1.0.0"

def _generate_changelog_with_semantic_release() -> bool:
    """Tenta gerar o changelog usando python-semantic-release."""
    try:
        # Verificar se semantic-release está instalado
        result = subprocess.run(
            ["semantic-release", "--noop", "changelog"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            logger.warning("semantic-release não está disponível ou falhou")
            return False
            
        # Gerar changelog
        try:
            subprocess.run(
                ["semantic-release", "changelog"],
                check=True,
                capture_output=True,
                text=True
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"Erro ao executar semantic-release changelog: {e.stderr}")
            return False
        
        return os.path.exists(CHANGELOG_FILE)
    except Exception as e:
        logger.error(f"Erro ao gerar changelog com semantic-release: {str(e)}")
        return False

def _generate_changelog_with_git_analyzer() -> bool:
    """Gera o changelog usando GitAnalyzer como fallback."""
    try:
        git_analyzer.generate_changelog(CHANGELOG_FILE)
        git_analyzer.save_version_info(VERSION_FILE)
        return os.path.exists(CHANGELOG_FILE)
    except Exception as e:
        logger.error(f"Erro ao gerar changelog com GitAnalyzer: {str(e)}")
        return False

def _parse_changelog_content() -> List[ChangelogEntry]:
    """Analisa o conteúdo do arquivo CHANGELOG.md e converte para o formato da API."""
    entries = []
    
    try:
        # Garantir que o arquivo CHANGELOG.md existe
        if not os.path.exists(CHANGELOG_FILE):
            # Tentar gerar o changelog primeiro com semantic-release
            if not _generate_changelog_with_semantic_release():
                # Se falhar, usar GitAnalyzer como fallback
                _generate_changelog_with_git_analyzer()
            
        # Ler o changelog se ele existir
        if os.path.exists(CHANGELOG_FILE):
            with open(CHANGELOG_FILE, "r") as f:
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
                            
                            if current_category in ["BREAKING CHANGES", "⚠ BREAKING CHANGES"]:
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
    except Exception as e:
        logger.error(f"Erro ao analisar changelog: {str(e)}")
    
    # Se não houver entradas, usar uma entrada padrão
    if not entries:
        entries = [
            ChangelogEntry(
                version="1.0.0",
                date="2024-06-10",
                changes=[
                    "Features: Versão inicial da API",
                    "Features: Implementação de autenticação com JWT",
                    "Features: Implementação de OAuth2 com Google",
                    "Features: Autenticação de dois fatores (MFA)",
                    "Features: Endpoints para documentos digitais",
                    "Features: Endpoints para cartão de transporte"
                ]
            )
        ]
    
    return entries

@router.get("", response_model=ChangelogResponse)
async def get_changelog(
    current_user: Optional[User] = Depends(get_current_user)
):
    """
    Retorna o histórico de mudanças da API.
    Útil para clientes acompanharem atualizações e migrações.
    """
    try:
        entries = _parse_changelog_content()
        api_version = _get_api_version()
        
        return ChangelogResponse(
            entries=entries,
            latest_version=entries[0].version if entries else "1.0.0",
            api_version=api_version
        )
    except Exception as e:
        logger.error(f"Erro ao gerar resposta de changelog: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao gerar changelog"
        )

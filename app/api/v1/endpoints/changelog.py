from fastapi import APIRouter, Depends, status, HTTPException
from typing import List, Dict, Optional
from pydantic import BaseModel
import os
import logging
import markdown

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

# Caminho para o arquivo
CHANGELOG_FILE = "CHANGELOG.md"

def _get_api_version() -> str:
    """Obtém a versão atual da API."""
    try:
        # Tentar obter da variável __version__
        import app
        return getattr(app, "__version__", "1.0.0")
    except Exception as e:
        logger.error(f"Erro ao obter versão da API: {str(e)}")
    
    return "1.0.0"

def _parse_changelog_content(content: str) -> List[ChangelogEntry]:
    """
    Analisa o conteúdo do changelog e retorna uma lista estruturada.
    
    Args:
        content: Conteúdo do arquivo CHANGELOG.md
        
    Returns:
        Lista de entradas do changelog
    """
    entries = []
    lines = content.split("\n")
    
    current_entry = None
    current_section = None
    changes = []
    breaking_changes = []
    deprecations = []
    
    for line in lines:
        # Nova versão
        if line.startswith("## "):
            # Salvar entrada anterior
            if current_entry:
                entries.append(ChangelogEntry(
                    version=current_entry["version"],
                    date=current_entry["date"],
                    changes=changes,
                    breaking_changes=breaking_changes if breaking_changes else None,
                    deprecations=deprecations if deprecations else None
                ))
                
                # Resetar listas
                changes = []
                breaking_changes = []
                deprecations = []
            
            # Extrair versão e data
            version_line = line[3:].strip()
            version_parts = version_line.split("(")
            
            version = version_parts[0].strip()
            if version == "Unreleased":
                version = "próxima"
                
            date = version_parts[1].replace(")", "").strip() if len(version_parts) > 1 else ""
            
            current_entry = {
                "version": version,
                "date": date
            }
            current_section = None
            
        # Nova seção
        elif line.startswith("### "):
            current_section = line[4:].strip()
            
        # Item da lista
        elif line.startswith("* ") and current_section:
            item = line[2:].strip()
            
            if current_section == "⚠ BREAKING CHANGES":
                breaking_changes.append(item)
            elif "Deprecations" in current_section:
                deprecations.append(item)
            else:
                changes.append(f"{current_section}: {item}")
    
    # Adicionar a última entrada
    if current_entry and (changes or breaking_changes or deprecations):
        entries.append(ChangelogEntry(
            version=current_entry["version"],
            date=current_entry["date"],
            changes=changes,
            breaking_changes=breaking_changes if breaking_changes else None,
            deprecations=deprecations if deprecations else None
        ))
    
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
        # Garantir que o arquivo CHANGELOG.md existe e está atualizado
        git_analyzer = GitAnalyzer()
        git_analyzer.update_changelog(CHANGELOG_FILE)
        
        # Verificar se o arquivo existe
        if not os.path.exists(CHANGELOG_FILE):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Arquivo de changelog não encontrado"
            )
        
        # Ler o conteúdo do arquivo
        with open(CHANGELOG_FILE, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Processar o conteúdo do arquivo
        changelog_entries = _parse_changelog_content(content)
        
        if not changelog_entries:
            # Fallback para um changelog básico
            changelog_entries = [
                ChangelogEntry(
                    version="0.1.0",
                    date=git_analyzer.generate_version_info()["date"].split()[0],
                    changes=["Versão inicial da API"]
                )
            ]
            
        # Obter a última versão
        latest_version = git_analyzer.get_api_version_from_tags()
        
        return ChangelogResponse(
            entries=changelog_entries,
            latest_version=latest_version,
            api_version=_get_api_version()
        )
        
    except Exception as e:
        logger.error(f"Erro ao processar changelog: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao processar changelog"
        )
        
@router.get("/html", response_model=Dict[str, str])
async def get_changelog_html(
    current_user: Optional[User] = Depends(get_current_user)
):
    """
    Retorna o changelog em formato HTML.
    Útil para exibição direta em aplicações web.
    """
    try:
        # Garantir que o arquivo CHANGELOG.md existe e está atualizado
        git_analyzer = GitAnalyzer()
        git_analyzer.update_changelog(CHANGELOG_FILE)
        
        # Ler o conteúdo do arquivo
        if not os.path.exists(CHANGELOG_FILE):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Arquivo de changelog não encontrado"
            )
            
        with open(CHANGELOG_FILE, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Converter Markdown para HTML
        html_content = markdown.markdown(content)
        
        return {"html": html_content}
        
    except Exception as e:
        logger.error(f"Erro ao processar changelog HTML: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao processar changelog HTML"
        )

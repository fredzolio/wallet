import subprocess
import re
from typing import List, Dict, Optional, Tuple
import os
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)

class GitAnalyzer:
    """
    Analisador de histórico Git para geração automática de changelogs.
    Utiliza o padrão Conventional Commits para estruturar as mudanças.
    """
    
    def __init__(self, repo_path: str = "."):
        """
        Inicializa o analisador Git.
        
        Args:
            repo_path: Caminho para o repositório Git
        """
        self.repo_path = repo_path
        
    def _run_git_command(self, command: List[str]) -> str:
        """
        Executa um comando git e retorna a saída.
        
        Args:
            command: Lista com o comando git a ser executado
            
        Returns:
            String com a saída do comando
        """
        try:
            result = subprocess.run(
                ["git"] + command,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.error(f"Erro ao executar comando git: {e}")
            return ""
    
    def get_tags(self) -> List[str]:
        """
        Obtém todas as tags do repositório ordenadas semanticamente.
        
        Returns:
            Lista de tags
        """
        tags = self._run_git_command(["tag", "--sort=-v:refname"])
        return tags.split("\n") if tags else []
    
    def get_latest_tag(self) -> Optional[str]:
        """
        Obtém a tag mais recente do repositório.
        
        Returns:
            Tag mais recente ou None se não houver
        """
        tags = self.get_tags()
        return tags[0] if tags else None
    
    def parse_conventional_commit(self, commit_message: str) -> Dict:
        """
        Analisa uma mensagem de commit no formato Conventional Commits.
        
        Args:
            commit_message: Mensagem de commit para análise
            
        Returns:
            Dicionário com os dados estruturados do commit
        """
        # Pattern para Conventional Commits
        pattern = r"^(?P<type>feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(?:\((?P<scope>[^\)]+)\))?: (?P<description>.+)(?:\n\n(?P<body>[\s\S]*))?(?:\n\n(?P<footer>BREAKING CHANGE: [\s\S]*))?$"
        
        match = re.match(pattern, commit_message, re.MULTILINE)
        if not match:
            # Fallback para commits que não seguem o padrão
            return {
                "type": "other",
                "scope": None,
                "description": commit_message.split("\n")[0],
                "body": None,
                "footer": None,
                "breaking": False
            }
        
        data = match.groupdict()
        
        # Verificar se é uma mudança que quebra compatibilidade
        breaking = bool(data.get("footer") and "BREAKING CHANGE:" in data.get("footer", ""))
        breaking = breaking or commit_message.startswith("BREAKING CHANGE:") or "!" in data.get("type", "")
        
        return {
            "type": data.get("type", "other"),
            "scope": data.get("scope"),
            "description": data.get("description", ""),
            "body": data.get("body"),
            "footer": data.get("footer"),
            "breaking": breaking
        }
    
    def get_commits_between_tags(self, start_tag: Optional[str] = None, end_tag: str = "HEAD") -> List[Dict]:
        """
        Obtém todos os commits entre duas tags.
        
        Args:
            start_tag: Tag de início (exclusiva)
            end_tag: Tag de fim (inclusiva), padrão é HEAD
            
        Returns:
            Lista de commits estruturados
        """
        range_spec = f"{start_tag}..{end_tag}" if start_tag else end_tag
        
        # Obter commits no formato --pretty
        format_str = "--pretty=format:%H%n%an%n%at%n%s%n%b%n==COMMIT_SEPARATOR=="
        commits_output = self._run_git_command(["log", range_spec, format_str])
        
        if not commits_output:
            return []
        
        # Separar commits individuais
        raw_commits = commits_output.split("==COMMIT_SEPARATOR==\n")
        
        # Parse de cada commit
        parsed_commits = []
        for raw_commit in raw_commits:
            if not raw_commit.strip():
                continue
                
            lines = raw_commit.split("\n")
            if len(lines) < 4:
                continue
                
            hash_id = lines[0]
            author = lines[1]
            timestamp = int(lines[2])
            date = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
            subject = lines[3]
            
            # Juntar as linhas restantes como o corpo
            body = "\n".join(lines[4:]) if len(lines) > 4 else ""
            
            # Mensagem completa para análise convencional
            full_message = f"{subject}\n\n{body}" if body else subject
            
            # Parsear mensagem de commit convencional
            commit_data = self.parse_conventional_commit(full_message)
            
            parsed_commits.append({
                "hash": hash_id,
                "author": author,
                "date": date,
                "subject": subject,
                "body": body,
                "type": commit_data["type"],
                "scope": commit_data["scope"],
                "description": commit_data["description"],
                "breaking": commit_data["breaking"]
            })
            
        return parsed_commits
    
    def generate_changelog(self, output_path: str = "CHANGELOG.md") -> str:
        """
        Gera um arquivo de changelog baseado no histórico Git.
        
        Args:
            output_path: Caminho para salvar o arquivo de changelog
            
        Returns:
            Conteúdo do changelog gerado
        """
        tags = self.get_tags()
        
        # Adicionar HEAD como tag mais recente para commits não lançados
        tags = ["HEAD"] + tags if tags else ["HEAD"]
        
        changelog = "# Changelog\n\n"
        
        # Para cada tag, obter commits até a tag anterior
        for i, current_tag in enumerate(tags):
            # Pular a última tag, pois não há "antes" dela
            if i >= len(tags) - 1:
                continue
                
            next_tag = tags[i + 1]
            
            # Se for HEAD e não houver commits, pular
            if current_tag == "HEAD" and not self._run_git_command(["log", "-1", "--oneline"]):
                continue
                
            # Título da versão
            version_title = "## Unreleased" if current_tag == "HEAD" else f"## {current_tag}"
            
            # Data do tag (ou atual para HEAD)
            if current_tag == "HEAD":
                date = datetime.now().strftime("%Y-%m-%d")
            else:
                date_output = self._run_git_command(["log", "-1", "--format=%ai", current_tag])
                date = datetime.fromisoformat(date_output.split()[0]).strftime("%Y-%m-%d")
                
            changelog += f"{version_title} ({date})\n\n"
            
            # Obter commits entre tags
            commits = self.get_commits_between_tags(next_tag, current_tag)
            
            # Classificar commits por tipo
            commit_types = {
                "feat": {"title": "Features", "commits": []},
                "fix": {"title": "Bug Fixes", "commits": []},
                "perf": {"title": "Performance Improvements", "commits": []},
                "refactor": {"title": "Code Refactoring", "commits": []},
                "docs": {"title": "Documentation", "commits": []},
                "style": {"title": "Styles", "commits": []},
                "test": {"title": "Tests", "commits": []},
                "build": {"title": "Build System", "commits": []},
                "ci": {"title": "Continuous Integration", "commits": []},
                "chore": {"title": "Chores", "commits": []},
                "revert": {"title": "Reverts", "commits": []},
                "other": {"title": "Other Changes", "commits": []}
            }
            
            breaking_changes = []
            
            for commit in commits:
                commit_type = commit["type"]
                
                # Se é um tipo conhecido, adicionar à categoria
                if commit_type in commit_types:
                    commit_types[commit_type]["commits"].append(commit)
                else:
                    commit_types["other"]["commits"].append(commit)
                    
                # Se for breaking change, adicionar à lista
                if commit["breaking"]:
                    breaking_changes.append(commit)
            
            # Adicionar breaking changes primeiro
            if breaking_changes:
                changelog += "### ⚠ BREAKING CHANGES\n\n"
                for commit in breaking_changes:
                    scope_txt = f"**{commit['scope']}:** " if commit["scope"] else ""
                    changelog += f"* {scope_txt}{commit['description']} ({commit['hash'][:7]})\n"
                changelog += "\n"
            
            # Adicionar outras categorias
            for type_key, type_data in commit_types.items():
                if not type_data["commits"]:
                    continue
                    
                changelog += f"### {type_data['title']}\n\n"
                
                for commit in type_data["commits"]:
                    scope_txt = f"**{commit['scope']}:** " if commit["scope"] else ""
                    changelog += f"* {scope_txt}{commit['description']} ({commit['hash'][:7]})\n"
                    
                changelog += "\n"
                
        # Salvar changelog se especificado
        if output_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(changelog)
                
        return changelog
    
    def get_api_version_from_tags(self) -> str:
        """
        Determina a versão atual da API baseado nas tags.
        
        Returns:
            Versão da API no formato semântico
        """
        latest_tag = self.get_latest_tag()
        
        # Se não há tag, usar 0.1.0
        if not latest_tag:
            return "0.1.0"
            
        # Limpar a tag (remover v prefixo se existir)
        version = latest_tag
        if version.startswith("v"):
            version = version[1:]
            
        return version
    
    def generate_version_info(self) -> Dict:
        """
        Gera informações de versão para a API.
        
        Returns:
            Dicionário com informações de versão
        """
        version = self.get_api_version_from_tags()
        
        # Obter último commit
        last_commit_hash = self._run_git_command(["rev-parse", "--short", "HEAD"])
        last_commit_date = self._run_git_command(["log", "-1", "--format=%ci"])
        
        # Verificar se há mudanças não commitadas
        dirty = bool(self._run_git_command(["status", "--porcelain"]))
        
        # Obter branch atual
        branch = self._run_git_command(["rev-parse", "--abbrev-ref", "HEAD"])
        
        return {
            "version": version,
            "commit": last_commit_hash,
            "date": last_commit_date,
            "dirty": dirty,
            "branch": branch
        }
        
    def save_version_info(self, output_path: str = "app/version.json") -> Dict:
        """
        Salva informações de versão em um arquivo JSON.
        
        Args:
            output_path: Caminho para salvar o arquivo de versão
            
        Returns:
            Dicionário com informações de versão
        """
        version_info = self.generate_version_info()
        
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(version_info, f, indent=2)
            
        return version_info

if __name__ == "__main__":
    analyzer = GitAnalyzer()
    analyzer.generate_changelog()
    analyzer.save_version_info() 
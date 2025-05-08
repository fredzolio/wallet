import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

async def run_migrations():
    """
    Executa as migrações do Alembic assincronamente.
    
    Esta função é responsável por garantir que o esquema do banco de dados
    esteja atualizado através da execução das migrações do Alembic.
    
    Returns:
        bool: True se as migrações foram aplicadas com sucesso, False caso contrário.
    
    Raises:
        Exception: Se ocorrer um erro durante a execução das migrações.
    """
    logger.info("Aplicando migrações do banco de dados...")
    try:
        # Verificar se o diretório de migrações existe
        alembic_dir = Path("alembic")
        if not alembic_dir.exists() or not alembic_dir.is_dir():
            logger.error("Diretório de migrações 'alembic' não encontrado.")
            raise FileNotFoundError("Diretório de migrações 'alembic' não encontrado.")
            
        # Executar migrações Alembic assincronamente
        process = await asyncio.create_subprocess_exec(
            "alembic", "upgrade", "head",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            logger.info("Migrações aplicadas com sucesso!")
            if stdout:
                logger.debug(f"Saída das migrações: {stdout.decode().strip()}")
            return True
        else:
            error_msg = stderr.decode().strip() if stderr else "Código de saída não-zero"
            logger.error(f"Erro ao aplicar migrações: {error_msg}")
            raise Exception(f"Falha ao aplicar migrações Alembic: {error_msg}")
            
    except Exception as e:
        logger.error(f"Erro ao aplicar migrações: {str(e)}")
        raise 
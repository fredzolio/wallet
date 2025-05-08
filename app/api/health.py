import time
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.session import get_db

router = APIRouter()

@router.get("/health", response_model=dict)
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    Verifica a saúde da aplicação.
    - Disponibilidade do banco de dados
    - Tempo de resposta
    """
    start_time = time.time()
    
    # Verifica conexão com o banco de dados
    try:
        # Executa uma query simples no banco
        result = await db.execute(text("SELECT 1"))
        db_status = "online" if result.scalar() == 1 else "offline"
    except Exception:
        db_status = "offline"
    
    # Calcula o tempo de resposta
    response_time = time.time() - start_time
    
    return {
        "status": "ok",
        "database": db_status,
        "response_time_ms": round(response_time * 1000, 2),
        "timestamp": time.time()
    }

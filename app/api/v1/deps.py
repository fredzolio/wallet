from slowapi import Limiter
from slowapi.util import get_remote_address
from redis.asyncio import Redis
from redis.asyncio.lock import Lock

from app.core.config import settings

# Conexão com Redis
redis = Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    decode_responses=True
)

# Configuração do rate limiter usando Redis como storage
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}"
)

async def get_redis_lock(resource_name: str, expire: int = 60) -> Lock:
    """
    Obtém um lock distribuído usando Redis.
    Útil para operações que precisam de exclusão mútua entre instâncias.
    
    Args:
        resource_name: Nome do recurso a ser bloqueado
        expire: Tempo de expiração do lock em segundos
        
    Returns:
        Um objeto Lock do Redis
    """
    return redis.lock(f"lock:{resource_name}", timeout=expire)

async def increment_counter(key: str, expire_seconds: int = 86400) -> int:
    """
    Incrementa um contador no Redis e define um tempo de expiração.
    Útil para estatísticas e contadores.
    
    Args:
        key: Chave do contador
        expire_seconds: Tempo de expiração em segundos (default: 1 dia)
        
    Returns:
        O valor atual do contador
    """
    pipe = redis.pipeline()
    await pipe.incr(key)
    await pipe.expire(key, expire_seconds)
    result = await pipe.execute()
    return result[0]  # Valor do INCR

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from jose import jwt
import uuid

from app.core.config import settings
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User

# OAuth2 scheme para extração do token do cabeçalho de autorização
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Dependência para obter o usuário atual a partir do token JWT.
    Valida o token e busca o usuário no banco de dados.
    """
    # Erro padrão de autenticação
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Decodificar o token
    payload = decode_token(token)
    if not payload:
        raise credentials_exception
    
    # Verificar se é um token de acesso
    token_type = payload.get("type")
    if token_type != "access":
        raise credentials_exception
    
    # Extrair o ID do usuário
    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise credentials_exception
    
    # Buscar o usuário no banco de dados com eager loading para transport_card
    stmt = select(User).where(User.id == user_uuid).options(selectinload(User.transport_card))
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
    
    # Verificar se o usuário está ativo
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário inativo"
        )
    
    return user

async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Dependência para garantir que o usuário está ativo.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário inativo"
        )
    return current_user

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4
import secrets
from starlette.responses import RedirectResponse
from httpx import AsyncClient
from jwt import decode
import uuid

from app.core.security import (
    hash_password, 
    verify_password, 
    create_access_token, 
    create_refresh_token,
    oauth,
    generate_mfa_secret,
    get_totp_uri,
    verify_totp,
    decode_token
)
from app.core.deps import get_current_user
from app.db.session import get_db
from app.api.v1.deps import redis, limiter
from app.models.user import User
from app.schemas.auth import (
    UserCreate, 
    UserResponse, 
    Token, 
    RefreshToken,
    MFASetup,
    MFAVerify,
    MFALogin,
    KeycloakToken
)
from app.core.keycloak import keycloak_client
from app.core.config import settings

router = APIRouter(prefix="/auth")

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def register(
    request: Request,
    user_in: UserCreate, 
    db: AsyncSession = Depends(get_db)
):
    """
    Registra um novo usuário com email e senha.
    """
    # Verifica se o email já está em uso
    result = await db.execute(select(User).where(User.email == user_in.email))
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email já registrado"
        )
    
    # Cria o usuário
    user = User(
        email=user_in.email,
        hashed_password=hash_password(user_in.password),
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    return UserResponse(
        id=str(user.id),
        email=user.email,
        is_active=user.is_active,
        has_mfa=bool(user.mfa_secret)
    )

@router.post("/login", response_model=Token)
@limiter.limit("15/minute")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """
    Realiza o login do usuário e retorna os tokens de acesso e refresh.
    """
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Autenticação de dois fatores necessária. Use o endpoint /auth/login-mfa"
        )
    
    access_token = create_access_token(user.id)
    refresh_token_jwt = create_refresh_token(user.id)
    
    decoded_payload_for_jti = decode_token(refresh_token_jwt)
    if not decoded_payload_for_jti or "jti" not in decoded_payload_for_jti:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Falha ao gerar JTI para refresh token")
    refresh_jti = decoded_payload_for_jti["jti"]
    
    await redis.set(f"refresh_token_jti:{refresh_jti}", str(user.id), ex=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60)
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token_jwt,
        token_type="bearer"
    )

@router.post("/login-mfa", response_model=Token)
@limiter.limit("10/minute")
async def login_mfa(
    request: Request,
    mfa_data: MFALogin,
    db: AsyncSession = Depends(get_db)
):
    """
    Login com autenticação de dois fatores (MFA).
    """
    result = await db.execute(select(User).where(User.email == mfa_data.username))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(mfa_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos"
        )
    
    if not user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário não tem MFA configurado. Use o endpoint /auth/login"
        )
    
    if not verify_totp(mfa_data.code, user.mfa_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Código MFA inválido"
        )
    
    access_token = create_access_token(user.id)
    refresh_token_jwt = create_refresh_token(user.id)

    decoded_payload_for_jti = decode_token(refresh_token_jwt)
    if not decoded_payload_for_jti or "jti" not in decoded_payload_for_jti:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Falha ao obter JTI do refresh token para MFA login")
    refresh_jti = decoded_payload_for_jti["jti"]

    await redis.set(f"refresh_token_jti:{refresh_jti}", str(user.id), ex=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60)
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token_jwt,
        token_type="bearer"
    )

@router.post("/refresh", response_model=Token)
@limiter.limit("20/minute")
async def refresh(
    request: Request,
    refresh_data: RefreshToken,
    db: AsyncSession = Depends(get_db)
):
    """
    Usa um refresh token (JWT) para obter um novo par de tokens.
    """
    decoded_payload = decode_token(refresh_data.refresh_token)
    if not decoded_payload or decoded_payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido ou tipo incorreto")

    refresh_jti = decoded_payload.get("jti")
    if not refresh_jti:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido (sem jti)")

    is_blacklisted = await redis.exists(f"revoked_jti:{refresh_jti}")
    if is_blacklisted:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revogado (JTI blacklisted)")
    
    stored_user_id_bytes = await redis.get(f"refresh_token_jti:{refresh_jti}")
    if not stored_user_id_bytes:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido, expirado ou JTI não encontrado no Redis")
    
    user_id_str = stored_user_id_bytes.decode('utf-8')
    
    user = await db.get(User, uuid.UUID(user_id_str))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não encontrado ou inativo")
    
    new_access_token = create_access_token(user.id)
    new_refresh_token_jwt = create_refresh_token(user.id)
    
    new_decoded_payload = decode_token(new_refresh_token_jwt)
    if not new_decoded_payload or "jti" not in new_decoded_payload:
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Falha ao gerar JTI para novo refresh token")
    new_refresh_jti = new_decoded_payload["jti"]

    # Adicionar JTI antigo à blacklist e remover do set de tokens válidos
    await redis.setex(f"revoked_jti:{refresh_jti}", settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60, "1")
    await redis.delete(f"refresh_token_jti:{refresh_jti}") # Importante remover da lista de tokens válidos

    # Armazenar novo JTI do refresh token
    await redis.set(f"refresh_token_jti:{new_refresh_jti}", str(user.id), ex=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60)
    
    return Token(
        access_token=new_access_token,
        refresh_token=new_refresh_token_jwt,
        token_type="bearer"
    )

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    refresh_data: RefreshToken,
    current_user: User = Depends(get_current_user)
):
    """
    Realiza o logout do usuário, adicionando o JTI do refresh token à blacklist.
    """
    decoded_payload = decode_token(refresh_data.refresh_token)
    if not decoded_payload or decoded_payload.get("type") != "refresh" or "jti" not in decoded_payload:
        # Não levanta erro, apenas não faz nada se o token for inválido, pois o objetivo é logout.
        # Ou pode-se retornar um erro se o token for completamente malformado.
        # Para simplificar, se não puder decodificar ou não tiver JTI, não faz nada.
        return {"message": "Logout processado (token inválido ou sem JTI)."}

    refresh_jti = decoded_payload["jti"]
    
    # Adicionar JTI à blacklist e remover da lista de tokens ativos
    await redis.setex(f"revoked_jti:{refresh_jti}", settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60, "1")
    await redis.delete(f"refresh_token_jti:{refresh_jti}") # Importante remover da lista de tokens válidos
    
    return {"message": "Logout realizado com sucesso"}

@router.post("/mfa/setup", response_model=MFASetup)
async def setup_mfa(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Configura autenticação de dois fatores (MFA) para o usuário.
    Retorna um segredo e URI para QR code.
    """
    if current_user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA já configurado para este usuário"
        )
    
    # Gerar segredo MFA
    mfa_secret = generate_mfa_secret()
    
    # Atualizar usuário com segredo (ainda não ativado)
    current_user.mfa_secret = mfa_secret
    await db.commit()
    
    # Gerar URI para QR code
    qr_code_uri = get_totp_uri(mfa_secret, current_user.email)
    
    return MFASetup(
        mfa_secret=mfa_secret,
        qr_code_uri=qr_code_uri
    )

@router.post("/mfa/verify", status_code=status.HTTP_200_OK)
async def verify_mfa(
    verify_data: MFAVerify,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Verifica um código MFA para ativar a autenticação de dois fatores.
    """
    if not current_user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA não configurado. Configure primeiro com /auth/mfa/setup"
        )
    
    # Verificar código
    if not verify_totp(verify_data.code, current_user.mfa_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Código MFA inválido"
        )
    
    return {"message": "MFA verificado com sucesso"}

# Google OAuth login
@router.get("/google/login")
async def google_login(request: Request):
    """
    Inicia o fluxo de login com Google OAuth2.
    Redireciona para a tela de consentimento do Google.
    """
    if not oauth.google:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth não configurado"
        )
    
    redirect_uri = request.url_for("google_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get("/google/callback")
async def google_callback(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Callback do Google OAuth2. 
    Recebe o código de autorização e cria/loga o usuário.
    """
    if not oauth.google:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth não configurado"
        )
    
    # Obter token do Google
    token = await oauth.google.authorize_access_token(request)
    
    # Obter dados do usuário
    user_data = await oauth.google.parse_id_token(request, token)
    email = user_data.get("email")
    
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não foi possível obter o email do Google"
        )
    
    # Buscar usuário existente ou criar novo
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    
    if not user:
        # Criar novo usuário
        random_password = secrets.token_urlsafe(12)
        user = User(
            email=email,
            hashed_password=hash_password(random_password),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    
    # Criar tokens
    access_token = create_access_token(user.id)
    refresh_token_jwt = create_refresh_token(user.id)
    
    decoded_payload_for_jti = decode_token(refresh_token_jwt)
    if not decoded_payload_for_jti or "jti" not in decoded_payload_for_jti:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Falha ao obter JTI do refresh token para Google callback")
    refresh_jti = decoded_payload_for_jti["jti"]
    
    # Armazenar refresh token
    await redis.set(f"refresh_token_jti:{refresh_jti}", str(user.id), ex=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60)
    
    # Redirecionar para frontend com tokens
    frontend_url = "http://localhost:3000/oauth-callback"
    redirect_url = f"{frontend_url}?access_token={access_token}&refresh_token={refresh_token_jwt}"
    
    return RedirectResponse(url=redirect_url)

@router.post("/keycloak/login", response_model=KeycloakToken)
@limiter.limit("15/minute")
async def keycloak_login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """
    Realiza login usando o Keycloak.
    """
    if not settings.USE_KEYCLOAK:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Autenticação Keycloak não está habilitada"
        )
    
    try:
        token_data = await keycloak_client.authenticate_user(
            username=form_data.username,
            password=form_data.password
        )
        
        return KeycloakToken(
            access_token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
            token_type="bearer",
            expires_in=token_data["expires_in"]
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Falha na autenticação: {str(e)}"
        )

@router.post("/keycloak/refresh", response_model=KeycloakToken)
@limiter.limit("20/minute")
async def keycloak_refresh(
    request: Request,
    refresh_data: RefreshToken
):
    """
    Atualiza o token do Keycloak usando um refresh token.
    """
    if not settings.USE_KEYCLOAK:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Autenticação Keycloak não está habilitada"
        )
    
    try:
        async with AsyncClient() as client:
            response = await client.post(
                f"{keycloak_client.token_endpoint}",
                data={
                    "grant_type": "refresh_token",
                    "client_id": keycloak_client.client_id,
                    "client_secret": keycloak_client.client_secret,
                    "refresh_token": refresh_data.refresh_token
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Falha ao atualizar token"
                )
                
            token_data = response.json()
            
            return KeycloakToken(
                access_token=token_data["access_token"],
                refresh_token=token_data["refresh_token"],
                token_type="bearer",
                expires_in=token_data["expires_in"]
            )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Falha ao atualizar token: {str(e)}"
        )

@router.post("/keycloak/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def keycloak_register(
    request: Request,
    user_in: UserCreate
):
    """
    Registra um novo usuário no Keycloak.
    """
    if not settings.USE_KEYCLOAK:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Autenticação Keycloak não está habilitada"
        )
    
    try:
        # Criar usuário no Keycloak
        user_data = {
            "email": user_in.email,
            "password": user_in.password,
            "firstName": user_in.first_name if hasattr(user_in, 'first_name') else "",
            "lastName": user_in.last_name if hasattr(user_in, 'last_name') else ""
        }
        
        user_id = await keycloak_client.create_user(user_data)
        
        # Atribuir role padrão
        await keycloak_client.assign_role(user_id, "user")
        
        return UserResponse(
            id=user_id,
            email=user_in.email,
            is_active=True,
            has_mfa=False
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Falha ao registrar usuário: {str(e)}"
        )

@router.get("/keycloak/user-info")
async def keycloak_user_info(request: Request):
    """
    Obtém informações do usuário autenticado no Keycloak.
    """
    if not settings.USE_KEYCLOAK:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Autenticação Keycloak não está habilitada"
        )
    
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de acesso não fornecido"
        )
    
    # Extrair token
    token = auth_header.split(" ")[1]
    
    try:
        # Verificar token e obter informações do usuário
        token_data = await keycloak_client.verify_token(token)
        user_info = await keycloak_client.get_user_info(token)
        
        return {
            "user_id": token_data.get("sub"),
            "email": user_info.get("email"),
            "name": user_info.get("name", ""),
            "roles": token_data.get("realm_access", {}).get("roles", [])
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Falha ao obter informações do usuário: {str(e)}"
        )

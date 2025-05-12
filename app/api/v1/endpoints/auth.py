from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import secrets
from starlette.responses import HTMLResponse
import uuid
import qrcode
import io
import base64

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
)
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
        id=user.id,
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
    
    stored_user_id = await redis.get(f"refresh_token_jti:{refresh_jti}")
    if not stored_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido, expirado ou JTI não encontrado no Redis")
    
    # Converter para string se for bytes, manter como está se já for string
    if isinstance(stored_user_id, bytes):
        user_id_str = stored_user_id.decode('utf-8')
    else:
        user_id_str = stored_user_id
    
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
    
    # Gerar imagem QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_code_uri)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Converter imagem para base64
    buffered = io.BytesIO()
    img.save(buffered)
    qr_code_image = "data:image/png;base64," + base64.b64encode(buffered.getvalue()).decode()
    
    return MFASetup(
        mfa_secret=mfa_secret,
        qr_code_uri=qr_code_uri,
        qr_code_image=qr_code_image
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
    
    try:
        # Extrair código de autorização e verificar se está presente
        auth_code = request.query_params.get("code")
        if not auth_code:
            return HTMLResponse(content="""
            <!DOCTYPE html>
            <html>
                <head>
                    <title>Falha no Login</title>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <style>
                        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; text-align: center; background-color: #f8f9fa; }
                        .container { max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
                        h1 { color: #dc3545; }
                        p { margin: 20px 0; line-height: 1.5; }
                        .btn { display: inline-block; background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 20px; }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>Falha no Login</h1>
                        <p>Não foi possível obter o código de autorização do Google.</p>
                        <p>Por favor, tente novamente.</p>
                        <a href="/api/v1/auth/google/login" class="btn">Tentar Novamente</a>
                    </div>
                </body>
            </html>
            """, status_code=400)

        try:
            # Método padrão - tentar obter token e dados do usuário
            token = await oauth.google.authorize_access_token(request)
            resp = await oauth.google.get("https://www.googleapis.com/oauth2/v3/userinfo", token=token)
            user_data = resp.json() if hasattr(resp, 'json') else resp
        except Exception as token_error:
            if "mismatching_state" in str(token_error) or "state" in str(token_error).lower():
                if hasattr(oauth.google, '_client'):
                    oauth.google._client.client_kwargs['verify_state'] = False
                    try:
                        token = await oauth.google.authorize_access_token(request)
                        resp = await oauth.google.get("https://www.googleapis.com/oauth2/v3/userinfo", token=token)
                        user_data = resp.json() if hasattr(resp, 'json') else resp
                    except Exception:
                        return HTMLResponse(content="""
                        <!DOCTYPE html>
                        <html>
                            <head>
                                <title>Falha no Login</title>
                                <meta charset="UTF-8">
                                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                                <style>
                                    body { font-family: Arial, sans-serif; margin: 0; padding: 20px; text-align: center; background-color: #f8f9fa; }
                                    .container { max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
                                    h1 { color: #dc3545; }
                                    p { margin: 20px 0; line-height: 1.5; }
                                    .btn { display: inline-block; background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 20px; }
                                </style>
                            </head>
                            <body>
                                <div class="container">
                                    <h1>Falha no Login</h1>
                                    <p>Ocorreu um erro durante a autenticação com o Google.</p>
                                    <p>Por favor, tente novamente.</p>
                                    <a href="/api/v1/auth/google/login" class="btn">Tentar Novamente</a>
                                </div>
                            </body>
                        </html>
                        """, status_code=400)
                else:
                    return HTMLResponse(content="""
                    <!DOCTYPE html>
                    <html>
                        <head>
                            <title>Falha no Login</title>
                            <meta charset="UTF-8">
                            <meta name="viewport" content="width=device-width, initial-scale=1.0">
                            <style>
                                body { font-family: Arial, sans-serif; margin: 0; padding: 20px; text-align: center; background-color: #f8f9fa; }
                                .container { max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
                                h1 { color: #dc3545; }
                                p { margin: 20px 0; line-height: 1.5; }
                                .btn { display: inline-block; background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 20px; }
                            </style>
                        </head>
                        <body>
                            <div class="container">
                                <h1>Falha na Configuração</h1>
                                <p>Erro na configuração da autenticação com o Google.</p>
                                <p>Entre em contato com o suporte.</p>
                                <a href="/api/v1/auth/google/login" class="btn">Tentar Novamente</a>
                            </div>
                        </body>
                    </html>
                    """, status_code=500)
            else:
                return HTMLResponse(content=f"""
                <!DOCTYPE html>
                <html>
                    <head>
                        <title>Falha no Login</title>
                        <meta charset="UTF-8">
                        <meta name="viewport" content="width=device-width, initial-scale=1.0">
                        <style>
                            body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; text-align: center; background-color: #f8f9fa; }}
                            .container {{ max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
                            h1 {{ color: #dc3545; }}
                            p {{ margin: 20px 0; line-height: 1.5; }}
                            .btn {{ display: inline-block; background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 20px; }}
                            .error-details {{ font-size: 0.8em; color: #6c757d; margin-top: 20px; }}
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <h1>Falha no Login</h1>
                            <p>Ocorreu um erro durante a autenticação com o Google.</p>
                            <p>Por favor, tente novamente.</p>
                            <div class="error-details">Detalhes: {str(token_error)[:100]}</div>
                            <a href="/api/v1/auth/google/login" class="btn">Tentar Novamente</a>
                        </div>
                    </body>
                </html>
                """, status_code=400)
        
        email = user_data.get("email")
        
        if not email:
            return HTMLResponse(content="""
            <!DOCTYPE html>
            <html>
                <head>
                    <title>Falha no Login</title>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <style>
                        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; text-align: center; background-color: #f8f9fa; }
                        .container { max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
                        h1 { color: #dc3545; }
                        p { margin: 20px 0; line-height: 1.5; }
                        .btn { display: inline-block; background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 20px; }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>Falha no Login</h1>
                        <p>Não foi possível obter o email da sua conta Google.</p>
                        <p>Verifique as permissões e tente novamente.</p>
                        <a href="/api/v1/auth/google/login" class="btn">Tentar Novamente</a>
                    </div>
                </body>
            </html>
            """, status_code=400)
        
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
            return HTMLResponse(content="""
            <!DOCTYPE html>
            <html>
                <head>
                    <title>Falha na Geração de Token</title>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <style>
                        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; text-align: center; background-color: #f8f9fa; }
                        .container { max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
                        h1 { color: #dc3545; }
                        p { margin: 20px 0; line-height: 1.5; }
                        .btn { display: inline-block; background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 20px; }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>Falha na Geração de Token</h1>
                        <p>Não foi possível gerar o token de acesso.</p>
                        <p>Entre em contato com o suporte.</p>
                        <a href="/api/v1/auth/google/login" class="btn">Tentar Novamente</a>
                    </div>
                </body>
            </html>
            """, status_code=500)
        
        refresh_jti = decoded_payload_for_jti["jti"]
        
        # Armazenar refresh token
        await redis.set(f"refresh_token_jti:{refresh_jti}", str(user.id), ex=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60)
        
        # Exibir página de sucesso com os tokens
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
            <head>
                <title>Login Realizado com Sucesso</title>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; text-align: center; background-color: #f8f9fa; }}
                    .container {{ max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
                    h1 {{ color: #28a745; }}
                    p {{ margin: 20px 0; line-height: 1.5; }}
                    .token-box {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 10px 0; text-align: left; word-break: break-all; }}
                    h3 {{ margin: 10px 0; color: #007bff; }}
                    .btn {{ display: inline-block; background-color: #28a745; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 20px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Login Realizado com Sucesso</h1>
                    <p>Olá, <strong>{email}</strong>! Seu login foi realizado com sucesso.</p>
                    
                    <h3>Access Token:</h3>
                    <div class="token-box">{access_token}</div>
                    
                    <h3>Refresh Token:</h3>
                    <div class="token-box">{refresh_token_jwt}</div>
                    
                    <p>Guarde estes tokens em um local seguro. Eles são necessários para acessar os recursos protegidos da API.</p>
                    
                    <a href="javascript:void(0)" class="btn" onclick="copyTokens()">Copiar Tokens</a>
                    
                    <script>
                        function copyTokens() {{
                            const tokens = `Access Token: {access_token}\\n\\nRefresh Token: {refresh_token_jwt}`;
                            navigator.clipboard.writeText(tokens).then(function() {{
                                alert('Tokens copiados para a área de transferência!');
                            }}, function(err) {{
                                alert('Erro ao copiar tokens: ' + err);
                            }});
                        }}
                    </script>
                </div>
            </body>
        </html>
        """)
        
    except Exception as e:
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
            <head>
                <title>Falha no Login</title>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; text-align: center; background-color: #f8f9fa; }}
                    .container {{ max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
                    h1 {{ color: #dc3545; }}
                    p {{ margin: 20px 0; line-height: 1.5; }}
                    .btn {{ display: inline-block; background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 20px; }}
                    .error-details {{ font-size: 0.8em; color: #6c757d; margin-top: 20px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Falha no Login</h1>
                    <p>Ocorreu um erro inesperado durante a autenticação.</p>
                    <p>Por favor, tente novamente.</p>
                    <div class="error-details">Detalhes: {str(e)[:100]}</div>
                    <a href="/api/v1/auth/google/login" class="btn">Tentar Novamente</a>
                </div>
            </body>
        </html>
        """, status_code=500)
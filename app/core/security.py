from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext
import pyotp
from authlib.integrations.starlette_client import OAuth
import uuid

from app.core.config import settings

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth setup
oauth = OAuth()
if settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET:
    oauth.register(
        name="google",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

# Funções para hash e verificação de senha
def hash_password(password: str) -> str:
    """Cria um hash da senha fornecida."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a senha em texto plano corresponde ao hash armazenado."""
    return pwd_context.verify(plain_password, hashed_password)

# Funções para token JWT
def create_access_token(user_id: uuid.UUID) -> str:
    """
    Cria um token JWT de acesso com expiração configurada.
    """
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.utcnow() + expires_delta
    
    to_encode = {
        "sub": str(user_id),
        "exp": expire,
        "type": "access"
    }
    
    # Garantir que SECRET_KEY seja tratada como uma string
    secret_key = str(settings.SECRET_KEY) if settings.SECRET_KEY else ""
    
    encoded_jwt = jwt.encode(
        to_encode, 
        secret_key, 
        algorithm=settings.ALGORITHM
    )
    
    return encoded_jwt

def create_refresh_token(user_id: uuid.UUID) -> str:
    """
    Cria um token JWT de refresh com expiração configurada.
    """
    expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    expire = datetime.utcnow() + expires_delta
    
    to_encode = {
        "sub": str(user_id),
        "exp": expire,
        "type": "refresh",
        "jti": str(uuid.uuid4())
    }
    
    # Garantir que SECRET_KEY seja tratada como uma string
    secret_key = str(settings.SECRET_KEY) if settings.SECRET_KEY else ""
    
    encoded_jwt = jwt.encode(
        to_encode, 
        secret_key, 
        algorithm=settings.ALGORITHM
    )
    
    return encoded_jwt

def decode_token(token: str) -> dict | None:
    """
    Decodifica um token JWT e retorna o payload.
    Retorna None se o token for inválido.
    """
    try:
        # Garantir que SECRET_KEY seja tratada como uma string
        secret_key = str(settings.SECRET_KEY) if settings.SECRET_KEY else ""
        
        payload = jwt.decode(
            token, 
            secret_key, 
            algorithms=[settings.ALGORITHM]
        )
        return payload
    except JWTError:
        return None

# Funções para MFA TOTP
def generate_mfa_secret() -> str:
    """Gera um segredo base32 para uso com TOTP."""
    return pyotp.random_base32()

def get_totp_uri(secret: str, email: str) -> str:
    """
    Gera uma URI para QR code TOTP.
    Esta URI pode ser usada para criar um QR code para o app autenticador.
    """
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=settings.MFA_ISSUER)

def verify_totp(token: str, secret: str) -> bool:
    """
    Verifica se um token TOTP é válido para o segredo fornecido.
    """
    totp = pyotp.TOTP(secret)
    return totp.verify(token, valid_window=1)

import uuid
from pydantic import BaseModel, EmailStr, Field

class UserCreate(BaseModel):
    """Schema para criação de usuário."""
    email: EmailStr
    password: str = Field(..., min_length=8)

class UserLogin(BaseModel):
    """Schema para login de usuário."""
    username: EmailStr  # OAuth2PasswordRequestForm usa 'username' para email
    password: str

class UserResponse(BaseModel):
    """Schema para resposta de usuário."""
    id: uuid.UUID
    email: EmailStr
    is_active: bool
    has_mfa: bool

    class Config:
        from_attributes = True

class Token(BaseModel):
    """Schema para token de autenticação."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshToken(BaseModel):
    """Schema para refresh token."""
    refresh_token: str

class MFASetup(BaseModel):
    """Schema para configuração de MFA."""
    mfa_secret: str
    qr_code_uri: str

class MFAVerify(BaseModel):
    """Schema para verificação de MFA."""
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")

class MFALogin(BaseModel):
    """Schema para login com MFA."""
    username: EmailStr
    password: str
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
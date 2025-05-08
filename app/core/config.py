import secrets
import json
from typing import List, Any
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, computed_field

class Settings(BaseSettings):
    # Configurações gerais
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Wallet API"
    
    # CORS - definido como string para evitar problemas de parsing
    CORS_ORIGINS_STR: str = "http://localhost:8000,http://localhost:3000"
    
    @computed_field
    @property
    def CORS_ORIGINS(self) -> List[str]:
        """Converte a string CORS_ORIGINS_STR em uma lista."""
        if not self.CORS_ORIGINS_STR:
            return ["http://localhost:8000", "http://localhost:3000"]
        return [origin.strip() for origin in self.CORS_ORIGINS_STR.split(",") if origin.strip()]
    
    # Database
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "wallet"
    POSTGRES_PASSWORD: str = "wallet"
    POSTGRES_DB: str = "wallet"
    DATABASE_URL: str | None = None  # Será carregado do .env
    
    @property
    def database_url(self) -> str:
        """
        Gera a URL do banco de dados se não for especificada.
        Certifica-se de usar o prefixo postgresql+asyncpg:// para conexões assíncronas.
        """
        if self.DATABASE_URL:
            return self.DATABASE_URL
        
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    # Redis (rate-limit & cache)
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    
    # Auth
    SECRET_KEY: str | None = None
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALGORITHM: str = "HS256"
    
    # OAuth2
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    OAUTH_CALLBACK_URL: str | None = None
    
    # Keycloak
    KEYCLOAK_URL: str | None = None
    KEYCLOAK_REALM: str | None = None
    KEYCLOAK_CLIENT_ID: str | None = None
    KEYCLOAK_CLIENT_SECRET: str | None = None
    USE_KEYCLOAK: bool = True
    
    # MFA
    MFA_ISSUER: str | None = None
    
    # Chatbot
    CHATBOT_DEFAULT_RESPONSES: dict = {
        "horario_atendimento": "O atendimento da prefeitura é de segunda a sexta, das 8h às 17h.",
        "endereco_prefeitura": "Rua Afonso Cavalcanti, 455 - Cidade Nova, Rio de Janeiro - RJ, 20211-110",
        "onde_pagar_iptu": "O IPTU pode ser pago em qualquer agência bancária ou casa lotérica até a data de vencimento."
    }
    
    # Google Generative AI para chatbot
    GOOGLE_GENAI_API_KEY: str | None = None
    GOOGLE_GENAI_MODEL: str = "gemini-2.0-flash"
    USE_LLM: bool = True
    
    # Prometheus
    ENABLE_PROMETHEUS: bool = True
    
    # Configuração para carregar de arquivo .env
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

# Instância global para uso em toda a aplicação
settings = Settings()

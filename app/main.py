from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.openapi.utils import get_openapi
from prometheus_fastapi_instrumentator import Instrumentator
import logging
from contextlib import asynccontextmanager

from app.api.health import router as health_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.documents import router as documents_router
from app.api.v1.endpoints.transport import router as transport_router
from app.api.v1.endpoints.chatbot import router as chatbot_router
from app.api.v1.endpoints.changelog import router as changelog_router
from app.core.config import settings
from app.db.init_db import init_db
from app.db.session import AsyncSessionLocal
from app.db.migrations import run_migrations

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# Configurar logger
logger = logging.getLogger(__name__)

# Configuração do rate limiter

limiter = Limiter(key_func=get_remote_address)

# Definir gerenciador de contexto para lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Aplicar migrações do banco de dados
    try:
        await run_migrations()
    except Exception as e:
        logger.error(f"Falha ao aplicar migrações: {e}")
        raise
    
    # Inicializar banco de dados
    logger.info("Inicializando banco de dados...")
    async with AsyncSessionLocal() as db:
        await init_db(db)
    logger.info("Banco de dados inicializado com sucesso!")
    yield

# Inicialização do aplicativo
app = FastAPI(
    title="Wallet API",
    description="API para Carteira Digital da Prefeitura do Rio de Janeiro",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

# Configuração do limiter
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=429,
        content={"detail": "Limite de requisições excedido. Tente novamente mais tarde."},
    )

app.add_middleware(SlowAPIMiddleware)

# Configuração CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rotas Swagger e ReDoc personalizadas
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
        init_oauth={
            "clientId": "",
            "usePkceWithAuthorizationCodeGrant": True,
        },
        swagger_ui_parameters={
            "docExpansion": "none",
            "deepLinking": True,
            "persistAuthorization": True,
        },
        custom_js="""
        window.onload = function() {
          // Adicionar instruções de MFA após o carregamento
          setTimeout(function() {
            const authBtn = document.getElementsByClassName("btn authorize")[0];
            if (authBtn) {
              const mfaHint = document.createElement("div");
              mfaHint.innerHTML = "<small style='color:#999'>Para MFA: use o formato senha:código no campo Password</small>";
              mfaHint.style.marginTop = "5px";
              authBtn.parentNode.appendChild(mfaHint);
            }
          }, 1000);
        };
        """
    )

@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - ReDoc",
        redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js",
    )

# Inclusão das rotas
app.include_router(health_router, tags=["Health"])
app.include_router(auth_router, prefix="/api/v1", tags=["Autenticação"])
app.include_router(documents_router, prefix="/api/v1", tags=["Documentos"])
app.include_router(transport_router, prefix="/api/v1", tags=["Transporte"])
app.include_router(chatbot_router, prefix="/api/v1", tags=["Chatbot"])
app.include_router(changelog_router, prefix="/api/v1", tags=["Changelog"])

# Descrição da API personalizada
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    
    # Adicionar componente de segurança para MFA
    if "components" not in openapi_schema:
        openapi_schema["components"] = {}
    
    if "securitySchemes" not in openapi_schema["components"]:
        openapi_schema["components"]["securitySchemes"] = {}
    
    # Adicionar esquema de segurança OAuth2 com MFA
    openapi_schema["components"]["securitySchemes"]["OAuth2PasswordBearer"] = {
        "type": "oauth2",
        "flows": {
            "password": {
                "tokenUrl": f"{settings.API_V1_STR}/auth/login",
                "scopes": {}
            },
            "implicit": {
                "authorizationUrl": f"{settings.API_V1_STR}/auth/login-mfa",
                "scopes": {}
            }
        },
        "description": "Autenticação padrão ou com MFA. Use login-mfa para autenticação de dois fatores."
    }
    
    # Aplicar segurança global
    openapi_schema["security"] = [{"OAuth2PasswordBearer": []}]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

# Em vez de substituir diretamente o método, alteramos o comportamento da API
app.openapi_schema = None  # Garantir que o esquema está limpo
setattr(app, "openapi", custom_openapi)

# Configuração do Prometheus (métricas)
if settings.ENABLE_PROMETHEUS:
    instrumentator = Instrumentator()
    instrumentator.instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    
    # Métricas personalizadas
    from prometheus_client import Counter, Histogram
    import time
    
    # Contador de requisições por endpoint
    REQUESTS_COUNTER = Counter(
        "wallet_api_requests_total",
        "Total de requisições por endpoint",
        ["endpoint", "method", "status_code"]
    )
    
    # Histograma de tempo de resposta
    RESPONSE_TIME = Histogram(
        "wallet_api_response_time_seconds",
        "Tempo de resposta em segundos",
        ["endpoint", "method"]
    )
    
    @app.middleware("http")
    async def add_metrics(request, call_next):
        # Registrar tempo de início
        start_time = time.time()
        
        # Processar requisição
        response = await call_next(request)
        
        # Registrar métricas
        endpoint = request.url.path
        method = request.method
        status_code = response.status_code
        
        # Incrementar contador de requisições
        REQUESTS_COUNTER.labels(endpoint=endpoint, method=method, status_code=status_code).inc()
        
        # Registrar tempo de resposta
        RESPONSE_TIME.labels(endpoint=endpoint, method=method).observe(time.time() - start_time)
        
        return response

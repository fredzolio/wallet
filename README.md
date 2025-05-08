# Wallet API – FastAPI / PostgreSQL

API para Carteira Digital da Prefeitura do Rio de Janeiro, permitindo armazenamento de documentos digitais, gestão de transporte público e chatbot para serviços municipais.

## Funcionalidades

- **Autenticação e Gestão de Usuários**
  - Login com email/senha
  - Autenticação com JWT
  - OAuth2 (Google)
  - Multi-factor authentication (MFA TOTP)
  
- **Documentos Digitais**
  - Upload e listagem de documentos

- **Transporte Público**
  - Consulta de saldo
  - Recarga de créditos

- **Chatbot**
  - Interface para perguntas e respostas sobre serviços municipais

## Tecnologias

- FastAPI
- PostgreSQL + SQLAlchemy + Alembic
- Redis (rate limiting)
- Docker & Docker Compose
- Autenticação: JWT, OAuth2, MFA TOTP
- Testes: Pytest, HTTPx, Fakeredis

## Estrutura do Projeto

```
wallet_api/
├── app/
│   ├── main.py                    # FastAPI, middlewares, routers
│   ├── core/                      # Configurações, segurança, dependências
│   ├── db/                        # SQLAlchemy, sessões, migrations
│   ├── models/                    # Modelos SQLAlchemy
│   ├── schemas/                   # Schemas Pydantic
│   ├── services/                  # Lógica de negócio
│   ├── api/                       # Endpoints da API
│   │   ├── v1/
│   │   │   ├── endpoints/         # Rotas da API v1
│   │   └── health.py              # Health check endpoint
│   └── tests/                     # Testes automatizados
```

## Como executar

### Com Docker

```bash
# Iniciar todos os serviços
docker-compose up -d

# Acessar Swagger UI
# http://localhost:8000/docs
```

### Desenvolvimento local

```bash
# Iniciar PostgreSQL e Redis
docker-compose up -d db redis

# Configurar ambiente virtual
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# ou
# .venv\Scripts\activate  # Windows

# Instalar dependências
pip install -e ".[test]"

# Aplicar migrações
alembic upgrade head

# Iniciar API em modo desenvolvimento
uvicorn app.main:app --reload
```

## Variáveis de Ambiente

Copie o arquivo `.env.example` para `.env` e ajuste as configurações:

```bash
cp .env.example .env
```

## Testes

```bash
# Executar todos os testes
pytest

# Com cobertura
pytest --cov=app
```

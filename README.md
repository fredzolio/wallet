# Wallet API - Carteira Digital da Prefeitura do Rio de Janeiro - Frederico Zolio

## Visão Geral

Este projeto implementa uma API para Carteira Digital que permite aos cidadãos do Rio de Janeiro gerenciar documentos digitais, consultar e recarregar passes de transporte público, além de interagir com um chatbot para esclarecimento de dúvidas sobre serviços municipais.

A API está disponível para testes em: [http://apiwallet.duckdns.org:8000/docs](http://apiwallet.duckdns.org:8000/docs)

### Ambientes de Demonstração Disponíveis

Os seguintes serviços estão disponíveis para acesso:

- **API**: [http://apiwallet.duckdns.org:8000/](http://apiwallet.duckdns.org:8000/) - API principal
- **PostgreSQL**: [http://apiwallet.duckdns.org:5432/](http://apiwallet.duckdns.org:5432/) - Banco de dados
- **Redis**: [http://apiwallet.duckdns.org:6379/](http://apiwallet.duckdns.org:6379/) - Cache e rate limiting
- **PG Admin**: [http://apiwallet.duckdns.org:5050/](http://apiwallet.duckdns.org:5050/) - Interface de gerenciamento do PostgreSQL (credenciais: fredzolio@live.com / admin)
- **Prometheus**: [http://apiwallet.duckdns.org:9090/](http://apiwallet.duckdns.org:9090/) - Coleta de métricas
- **Grafana**: [http://apiwallet.duckdns.org:3001/](http://apiwallet.duckdns.org:3001/) - Dashboards de monitoramento (credenciais: admin / admin)
  - [Dashboard Principal](http://apiwallet.duckdns.org:3001/d/wallet-api-dashboard/wallet-api-dashboard?orgId=1&refresh=5s) - Dashboard específico com métricas da API

## Decisões Arquiteturais

### Arquitetura em Camadas

O projeto foi estruturado usando uma arquitetura em camadas clara que separa as responsabilidades:

- **API Layer**: Endpoints RESTful, validação de entrada e gerenciamento de rotas
- **Service Layer**: Lógica de negócios e regras da aplicação
- **Data Access Layer**: Interação com o banco de dados e persistência
- **Core**: Configurações, segurança e funcionalidades centrais

Esta separação permite melhor manutenibilidade, testabilidade e escalabilidade da aplicação.

### Design Patterns Aplicados

- **Repository Pattern**: Abstração das operações de banco de dados
- **Dependency Injection**: Utilizado via FastAPI para facilitar os testes e desacoplamento
- **Factory Pattern**: Para criação de objetos complexos
- **Middleware Pattern**: Para funcionalidades transversais como autenticação, rate limiting e métricas

## Escolhas Tecnológicas e Justificativas

- **FastAPI**: Framework moderno, rápido e assíncrono com geração automática de OpenAPI
- **SQLAlchemy + Asyncpg**: ORM assíncrono para melhor performance com PostgreSQL
- **Alembic**: Gerenciamento de migrações de banco de dados
- **JWT + OAuth2**: Autenticação segura com suporte a múltiplos provedores (Google)
- **Redis**: Cache, controle de rate limiting e armazenamento de refresh tokens
- **PyOTP + QRCode**: Implementação de autenticação de dois fatores (MFA)
- **Prometheus + Grafana**: Monitoramento e observabilidade da aplicação
- **Ruff + MyPy**: Garantia de qualidade de código com linting e type checking
- **UV**: Gerenciador de dependências moderno e rápido para Python
- **Docker + Docker Compose**: Containerização e orquestração local
- **GitHub Actions**: CI/CD automatizado

## Funcionalidades Implementadas

- **Autenticação e Usuários**
  - Registro e login com email/senha
  - Autenticação via OAuth2 (Google)
  - Autenticação de dois fatores (TOTP)
  - Refresh tokens e logout seguro

- **Gestão de Documentos**
  - Upload, listagem e remoção de documentos digitais
  - Validação de documentos
  - Controle de acesso por usuário

- **Gestão de Transporte Público**
  - Consulta de saldo
  - Recarga de passes
  - Histórico de transações

- **Chatbot Integrado**
  - Respostas a perguntas comuns sobre serviços municipais
  - Integração opcional com Google Gemini para respostas mais inteligentes

- **Changelog Automático**
  - Rastreamento de alterações na API
  - Disponibilização de mudanças em formatos JSON e HTML

## Testes e Qualidade

O projeto implementa uma estratégia abrangente de testes em múltiplas camadas:

- **Testes Unitários**: Validam a lógica de negócios isolada em funções e métodos específicos
- **Testes de Integração**: Verificam o funcionamento conjunto dos componentes, utilizando banco de dados SQLite em memória
- **Testes de API**: Validam endpoints e fluxos completos através de requisições HTTP simuladas

### Estrutura dos Testes

- **`conftest.py`**: Configuração central dos testes com:
  - Fixtures para banco de dados em memória (SQLite)
  - Mocks para Redis e rate limiting
  - Utilitários para criação de usuários e tokens de teste

- **Testes por Domínio**:
  - `test_auth.py`: Autenticação, proteção de rotas e tokens
  - `test_documents.py`: CRUD de documentos digitais
  - `test_transport.py`: Cartões de transporte, consultas de saldo e recargas

- **Recursos Especiais**:
  - Decorador `skip_on_redis_error` para garantir que testes possam ser executados mesmo sem Redis
  - Configuração assíncrona completa com `pytest-asyncio`
  - Cliente HTTP assíncrono para testes de endpoints

### Execução dos Testes

```bash
# Executar todos os testes
uv run pytest app/tests/ -v

# Executar testes que não dependem do Redis
uv run pytest -k "not redis" -v

# Executar testes de um módulo específico
uv run pytest app/tests/test_auth.py -v
```

- **Type Checking**: Verificação estática de tipos com MyPy
- **Linting**: Análise de código com Ruff

## CI/CD e DevOps

- **Pipeline Automatizado**:
  - Validação de código (linting, type checking)
  - Execução de testes
  - Build e publicação da imagem Docker
  
- **Monitoramento**:
  - Prometheus para coleta de métricas
  - Grafana para dashboards e visualização
  - Health checks para verificação de status

## Considerações sobre Escalabilidade

- **Design Assíncrono**: FastAPI e SQLAlchemy Async para alta performance
- **Banco de Dados Escalável**: PostgreSQL com suporte a sharding e particionamento
- **Containerização**: Facilidade para deploy em ambientes Kubernetes
- **Rate Limiting**: Proteção contra abusos e sobrecarga
- **Monitoramento**: Detecção precoce de gargalos de performance

## Requisitos para Execução

### Ambiente de Desenvolvimento

- Python 3.13+
- Docker e Docker Compose
- UV (gerenciador de pacotes Python)

### Configuração e Execução

1. Clone o repositório
   ```bash
   git clone https://github.com/fredzolio/wallet.git
   cd wallet
   ```

2. Configure as variáveis de ambiente
   ```bash
   cp .env.example .env
   # Edite o arquivo .env com suas configurações
   ```

3. Inicie os serviços com Docker Compose
   ```bash
   docker-compose up -d
   ```

4. Acesse a API em http://localhost:8000/docs

### Execução Local sem Docker

```bash
# Instale o UV (se ainda não tiver)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Instale as dependências
uv sync

# Execute as migrações do banco de dados
uv run -m alembic upgrade head

# Inicie o servidor
uv run uvicorn app.main:app --reload
```

## Documentação da API

A documentação completa da API está disponível em:

- **Swagger UI**: `/docs`
- **ReDoc**: `/redoc`

## Principais Rotas e Utilização

### Autenticação
- `POST /api/v1/auth/register` - Registrar novo usuário
- `POST /api/v1/auth/login` - Login com email/senha
- `POST /api/v1/auth/login-mfa` - Login com autenticação de dois fatores
- `GET /api/v1/auth/google/login` - Login via Google (Deve ser acessado diretamente no navegador através da URL http://apiwallet.duckdns.org:8000/api/v1/auth/google/login, não pelo Swagger)
- `POST /api/v1/auth/mfa/setup` - Configurar autenticação de dois fatores

### Documentos
- `POST /api/v1/documents/` - Fazer upload de documento
- `GET /api/v1/documents/` - Listar documentos do usuário
- `GET /api/v1/documents/{id}` - Obter documento específico
- `DELETE /api/v1/documents/{id}` - Remover documento

### Transporte
- `GET /api/v1/transport/balance` - Consultar saldo
- `POST /api/v1/transport/recharge` - Recarregar passe
- `GET /api/v1/transport/history` - Histórico de transações

### Chatbot
- `POST /api/v1/chatbot/ask` - Fazer pergunta ao chatbot

### Changelog
- `GET /api/v1/changelog` - Obter histórico de mudanças da API em formato estruturado
- `GET /api/v1/changelog/html` - Obter histórico de mudanças da API em formato HTML

Existem outros endpoints, consultar Swagger/OpenAPI.

## Qualidade de Código

O projeto segue padrões rigorosos de qualidade:

- Type hints em todo o código
- Documentação de funções e classes
- Padronização de estilos com Ruff
- Comentários explicativos para fácil manutenção do código
- Testes automatizados com alta cobertura
- Validação contínua via CI/CD

Para verificar a qualidade do código:

```bash
# Executar linting
uv run ruff check .

# Verificar tipos
uv run mypy app

# Executar todos os checks
uv run taskipy check
```

## Tasks Disponíveis

O projeto utiliza o `taskipy` para definir atalhos para comandos frequentemente utilizados durante o desenvolvimento. As seguintes tasks estão disponíveis:

```bash
# Gerar changelog baseado no histórico do Git
uv run taskipy changelog

# Executar verificação de linting com Ruff
uv run taskipy ruff

# Executar verificação e correção automática de linting
uv run taskipy ruff-fix

# Executar testes automatizados
uv run taskipy tests

# Executar verificação de tipos com MyPy
uv run taskipy mypy

# Executar verificação completa (linting, tipos e testes)
uv run taskipy check
```

Estas tasks facilitam o processo de desenvolvimento e garantem a qualidade do código antes de commits e envios para produção.

## Changelog Automático

O projeto implementa um sistema de changelog automatizado que rastreia e apresenta as mudanças da API:

- **Geração Automática**: Utiliza o histórico do Git para gerar o CHANGELOG.md quando o arquivo não existe
- **Endpoints Dedicados**: API RESTful para acessar o histórico de mudanças
  - `/api/v1/changelog`: Retorna o changelog em formato JSON estruturado
  - `/api/v1/changelog/html`: Retorna o changelog em formato HTML para integração direta em aplicações web
- **Compatibilidade**: Auxilia clientes a se adaptarem a novas versões e mudanças na API
- **Rastreamento de Breaking Changes**: Identifica alterações que podem impactar integrações existentes

Para gerar/atualizar o changelog manualmente:
```bash
uv run taskipy changelog
```

## Imagem da pipeline estruturada no Jenkins funcionando
![image](https://github.com/user-attachments/assets/0ab54f2b-ed7b-492b-a3ea-a6db5d6d13ad)

## Licença

Este projeto é distribuído sob a licença MIT.

## Contato

Para dúvidas ou sugestões, entre em contato com [frederico.zolio@prefeitura.rio](mailto:frederico.zolio@prefeitura.rio).

FROM python:3.13-slim

# Copiar uv diretamente da imagem oficial
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Instalar dependências do sistema necessárias
RUN apt-get update && apt-get install -y build-essential libpq-dev git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . /app

# Instalar dependências
RUN uv sync

# Criar e configurar script de entrada
RUN echo '#!/usr/bin/env bash\nset -euo pipefail\nuv run -m alembic upgrade head\nexec uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --loop uvloop --proxy-headers --forwarded-allow-ips=*' > /app/entrypoint.sh \
    && chmod +x /app/entrypoint.sh

EXPOSE 8000
CMD ["/app/entrypoint.sh"]

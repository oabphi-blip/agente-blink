# Lia Engineer Autônomo — Dockerfile pra Easypanel
#
# Build no root do repo:
#   docker build -f lia_engineer/Dockerfile -t blink-engineer:latest .
#
# Env vars obrigatórias em runtime:
#   ANTHROPIC_API_KEY, LIA_ENGINEER_GH_TOKEN, WEBHOOK_SECRET,
#   SLACK_WEBHOOK_LIA_ENGINEER_URL, KOMMO_TOKEN

FROM python:3.11-slim

WORKDIR /app

# Git é necessário pra apply_fix (commit + push)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates && rm -rf /var/lib/apt/lists/*

# Identidade Git pra commits (sobrescrevível por env)
RUN git config --global user.name "Lia Engineer (Bot)" && \
    git config --global user.email "lia-engineer@blinkoftalmologia.com.br"

# Copiar código
COPY pyproject.toml .
COPY voice_agent ./voice_agent
COPY lia_engineer ./lia_engineer
COPY tests ./tests
COPY CLAUDE.md .

# Instalar deps Python
RUN pip install --no-cache-dir anthropic requests python-dotenv

# Clonar repo na build seria errado — em runtime, o engineer clona se preciso.
# Por enquanto o repo é o próprio container. Push usa GH token via env.

# Loop daemon como entrypoint
CMD ["python", "-m", "lia_engineer.cli", "daemon"]

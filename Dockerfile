FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PORT=8000
WORKDIR /app
COPY requirements.txt /app/
RUN pip install -r /app/requirements.txt
# cache-bust 15/06/2026 13:42 BRT — fix(zep): corrige IndentationError linha 2311
ARG BUILD_REVISION=2026-06-15T15-30-watchdog-promessa
RUN echo "Build $BUILD_REVISION"
COPY voice_agent /app/voice_agent
EXPOSE 8000
CMD ["uvicorn","voice_agent.webhook:app","--host","0.0.0.0","--port","8000"]

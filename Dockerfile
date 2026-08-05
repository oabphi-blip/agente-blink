FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PORT=8000
WORKDIR /app
COPY requirements.txt /app/
RUN pip install -r /app/requirements.txt
# cache-bust 15/06/2026 13:42 BRT — fix(zep): corrige IndentationError linha 2311
ARG BUILD_REVISION=2026-06-15T16-00-fix-import
RUN echo "Build $BUILD_REVISION"
COPY voice_agent /app/voice_agent
COPY voice_agent/watchdog_promessa.py /app/watchdog_promessa.py
# CI gate — bloqueia deploy se master regressão falhar (Task #437)
COPY tests /app/tests
RUN pip install pytest -q \
    && python -m pytest tests/test_bugs_indexados_regressao_master.py -x -q \
    && echo "CI gate passed ✓" \
    && pip uninstall pytest -yq \
    && rm -rf /app/tests
EXPOSE 8000
CMD ["uvicorn","voice_agent.webhook:app","--host","0.0.0.0","--port","8000"]

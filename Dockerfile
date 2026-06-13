# 서버 풀 에이전트 (경량). 백엔드가 메트릭을 수집할 대상 한 대를 흉내낸다.
FROM python:3.12-slim

# uv (의존성 관리)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    PYTHONPATH=/code \
    PYTHONUNBUFFERED=1

WORKDIR /code

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

RUN useradd -m appuser && chown -R appuser:appuser /code /opt/venv
USER appuser

ENV PATH="/opt/venv/bin:$PATH"

# PORT는 컨테이너마다 다르게 주입된다(compose).
CMD ["sh", "-c", "uvicorn agent.main:app --host 0.0.0.0 --port ${PORT:-9101}"]

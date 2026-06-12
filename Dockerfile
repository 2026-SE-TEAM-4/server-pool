# 서버 풀 에이전트 (경량). 백엔드가 메트릭을 수집할 대상 한 대를 흉내낸다.
# 장애·부하 시연용으로 stress-ng, hey를 이미지에 포함한다.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends stress-ng curl ca-certificates \
    && curl -fsSL -o /usr/local/bin/hey https://storage.googleapis.com/hey-releases/hey_linux_amd64 \
    && chmod +x /usr/local/bin/hey \
    && rm -rf /var/lib/apt/lists/*

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

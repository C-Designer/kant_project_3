# EXP-0002: 모든 설정이 같은 이미지·같은 도구 버전으로 돈다. 설정마다 이 이미지로 컨테이너를 따로 띄운다.
FROM python:3.12-slim

# uv 버전을 로컬(0.13.6)과 같게 고정한다
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
COPY src ./src
COPY scripts ./scripts

# HF_HUB_OFFLINE: 모델 가중치는 호스트 캐시(읽기 전용 마운트)에서만 읽어 모든 컨테이너가 같은 가중치를 쓴다
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app UV_NO_SYNC=1 HF_HUB_OFFLINE=1 PYTHONUNBUFFERED=1

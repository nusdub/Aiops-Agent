FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir uv

# 复制依赖文件并安装 Python 依赖（不含项目源码）
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project || uv sync --no-dev --no-install-project

# 复制项目源码；先创建目标目录确保缺失时仍可构建
RUN mkdir -p /app/app /app/mcp_servers /app/static /app/aiops-docs
COPY app ./app
COPY mcp_servers ./mcp_servers
COPY static ./static
COPY aiops-docs ./aiops-docs

# 安装项目本身（使 app 包可导入）
RUN uv sync --frozen --no-dev || uv sync --no-dev \
    && mkdir -p /app/logs /app/uploads /app/data/chroma \
    && ( useradd -m -s /usr/sbin/nologin aiops 2>/dev/null \
      || useradd -m -s /sbin/nologin aiops 2>/dev/null \
      || useradd -m -s /bin/false aiops ) \
    && chown -R aiops:aiops /app

USER aiops

EXPOSE 9900 8010

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -fsS http://127.0.0.1:${PORT:-9900}/ready || exit 1

CMD ["sh", "-c", "python -m uvicorn app.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-9900}"]

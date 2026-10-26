# ---- 前端构建 ----
FROM node:24-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
# lockfile 中的 resolved 地址指向开发机的 npm 镜像，这里改用镜像内配置的 registry
RUN npm ci --replace-registry-host=always
COPY frontend/ ./
RUN npm run build

# ---- 运行时 ----
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.10.8 /uv /usr/local/bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/routeforge ./routeforge
RUN uv sync --frozen --no-dev
COPY --from=web /web/dist /app/static

ENV PATH="/app/.venv/bin:$PATH" \
    ROUTEFORGE_DATA_DIR=/data \
    ROUTEFORGE_STATIC_DIR=/app/static
VOLUME /data
EXPOSE 8000
CMD ["routeforge"]

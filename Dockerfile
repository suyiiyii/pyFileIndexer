# ============================================================================
# 阶段 1: 前端构建阶段
# ============================================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# 复制前端项目配置文件
COPY ./web/frontend/package*.json ./
COPY ./web/frontend/tsconfig*.json ./
COPY ./web/frontend/vite.config.ts ./

# 安装前端依赖（包括开发依赖，构建时需要）
RUN npm ci

# 复制前端源码并构建
COPY ./web/frontend/src ./src
COPY ./web/frontend/index.html ./
COPY ./web/frontend/public ./public

# 构建前端
RUN npm run build

# ============================================================================
# 阶段 2: 最终运行阶段
# ============================================================================
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS runtime

# 设置工作目录
WORKDIR /app

# 复制 Python 项目配置并安装依赖
COPY ./pyproject.toml ./uv.lock ./
RUN uv sync --frozen

# 复制应用代码
COPY ./pyFileIndexer ./pyFileIndexer
COPY ./web/backend ./web/backend

# 从前端构建阶段复制构建产物
COPY --from=frontend-builder /app/frontend/dist ./web/frontend/dist

# 创建非 root 用户并设置缓存目录权限
RUN groupadd -r appgroup && useradd -r -g appgroup appuser && \
    mkdir -p /home/appuser/.cache && \
    chown -R appuser:appgroup /app /home/appuser/.cache
USER appuser

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
ENTRYPOINT ["uv", "run", "python", "pyFileIndexer/main.py"]
CMD ["--help"]


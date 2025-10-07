# ============================================================================
# 阶段 1: 前端构建阶段
# ============================================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# 安装 pnpm
RUN npm install -g pnpm

# 复制前端项目配置文件
COPY ./frontend/package*.json ./
COPY ./frontend/pnpm-lock.yaml ./
COPY ./frontend/tsconfig*.json ./
COPY ./frontend/vite.config.ts ./
COPY ./frontend/tailwind.config.js ./
COPY ./frontend/eslint.config.js ./

# 安装前端依赖（包括开发依赖，构建时需要）
RUN pnpm install --frozen-lockfile

# 复制前端源码并构建
COPY ./frontend/src ./src
COPY ./frontend/index.html ./
COPY ./frontend/public ./public

# 构建前端
RUN pnpm run build

# ============================================================================
# 阶段 2: 最终运行阶段
# ============================================================================
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS runtime

# 安装 RAR 解压工具
RUN apt-get update && \
    apt-get install -y unar && \
    rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制 Python 项目配置并安装依赖
COPY ./pyproject.toml ./uv.lock ./
RUN uv sync --frozen

# 复制应用代码
COPY ./pyFileIndexer ./pyFileIndexer
# 后端代码已合并到pyFileIndexer目录中

# 从前端构建阶段复制构建产物
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
ENTRYPOINT ["uv", "run", "python", "pyFileIndexer/main.py"]
CMD ["--help"]


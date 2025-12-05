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

# 安装依赖
RUN pnpm install --frozen-lockfile

# 复制源码并构建
COPY ./frontend/src ./src
COPY ./frontend/index.html ./
COPY ./frontend/public ./public
RUN pnpm run build

# ============================================================================
# 阶段 2: 最终运行阶段
# ============================================================================
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS runtime

# 安装系统依赖 (UNAR)
RUN apt-get update && \
    apt-get install -y unar && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1. 先复制依赖定义文件 (利用 Docker 缓存层)
COPY ./pyproject.toml ./uv.lock ./

# 2. 安装依赖 (不安装项目本身，只安装 dependencies)
# --no-dev: 生产环境通常不需要开发依赖
# --no-install-project: 我们只需要环境，不需要把当前目录打包安装
RUN uv sync --frozen --no-dev --no-install-project

# 3. 复制源代码 (放在安装依赖之后，因为代码变动频繁)
COPY ./pyFileIndexer ./pyFileIndexer
# 如果你的入口逻辑完全在 pyFileIndexer 包里，其实不需要根目录的 main.py
# 但为了兼容你之前的结构，这里还是复制一下，如果没用到可以删除
COPY ./main.py ./

# 4. 复制前端产物
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# 暴露端口
EXPOSE 8000

# 将 .venv 添加到 PATH，这样可以直接使用 "python" 而不是 "/app/.venv/bin/python"
ENV PATH="/app/.venv/bin:$PATH"

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# ==================== 核心修改 ====================
# 使用 Exec 格式，并且直接调用 python，跳过 uv run 的构建检查
# 注意：这里假设你的入口是 pyFileIndexer.main 模块
ENTRYPOINT ["python", "-m", "pyFileIndexer.main"]

# CMD 作为默认参数传递给 ENTRYPOINT
# 用户运行时可以覆盖：docker run my-image scan /data
CMD ["--help"]
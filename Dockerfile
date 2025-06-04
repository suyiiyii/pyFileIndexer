FROM ghcr.io/astral-sh/uv:python3.11-bookworm

# 设置工作目录
WORKDIR /app

# 安装依赖
COPY ./pyproject.toml /app/
RUN uv sync

# 拷贝代码
COPY ./pyFileIndexer /app

# 启动
ENTRYPOINT ["poetry", "run", "python", "main.py"]
CMD ["--help"]


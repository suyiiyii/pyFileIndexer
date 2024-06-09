FROM python:3.11-slim

# 安装poetry
RUN pip install poetry

# 设置工作目录
WORKDIR /app

# 安装依赖
COPY ./pyproject.toml /app/
RUN poetry install

# 拷贝代码
COPY ./pyFileIndexer /app

# 启动
ENTRYPOINT ["poetry", "run", "python", "main.py"]
CMD ["--help"]


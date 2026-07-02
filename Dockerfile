# MyAPS API Dockerfile
# 多阶段构建，优化镜像体积

# 基础镜像源配置（可选使用国内镜像）
ARG PYTHON_IMAGE=python:3.12-slim

# 构建阶段
FROM ${PYTHON_IMAGE} AS builder

ARG USE_ALIYUN_MIRROR=false
RUN if [ "$USE_ALIYUN_MIRROR" = "true" ]; then \
    sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list 2>/dev/null || true; \
fi

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# 分层安装依赖，避免单层过大
RUN pip install --no-cache-dir --user fastapi "uvicorn[standard]" websockets tortoise-orm pydantic
RUN pip install --no-cache-dir --user aiomysql asyncpg python-dotenv requests tomlkit
RUN pip install --no-cache-dir --user apscheduler pandas mysql-replication
RUN pip install --no-cache-dir --user qrcode pillow python-barcode python-multipart
RUN pip install --no-cache-dir --user xlrd openpyxl pycryptodome
RUN pip install --no-cache-dir --user aiohttp httpx "httpx[http2]" psutil redis
RUN pip install --no-cache-dir --user gunicorn loguru prometheus-client

# 运行阶段
FROM ${PYTHON_IMAGE}

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libmariadb3 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/logs /app/storage /app/project_files

COPY --from=builder /root/.local /root/.local

ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/docs || exit 1

CMD ["gunicorn", "-c", "scripts/deploy/gunicorn.conf.py", "main:app"]

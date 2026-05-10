# MyAPS API Dockerfile
# 多阶段构建，优化镜像体积

# 构建阶段
FROM python:3.12-slim AS builder

WORKDIR /app

RUN sed -i 's/deb.debian.org/mirrors.tencentyun.com/g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip config set global.index-url http://mirrors.tencentyun.com/pypi/simple \
    && pip config set install.trusted-host mirrors.tencentyun.com \
    && pip install --no-cache-dir --user -r requirements.txt

# 运行阶段
FROM python:3.12-slim

WORKDIR /app

RUN sed -i 's/deb.debian.org/mirrors.tencentyun.com/g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
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

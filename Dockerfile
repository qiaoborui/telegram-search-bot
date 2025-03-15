# 构建阶段：安装依赖和编译
FROM python:3.9-slim AS builder

# 设置工作目录
WORKDIR /build

# 安装构建依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 升级pip
RUN pip install --no-cache-dir --upgrade pip wheel setuptools

# 只复制requirements.txt以利用缓存
COPY requirements.txt .

# 安装Python依赖到指定目录
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# 最终阶段：创建最小运行镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装运行时依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libpq5 \
    fonts-dejavu \
    fonts-noto-cjk \
    fonts-wqy-microhei \
    fonts-wqy-zenhei \
    fontconfig \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -f -v

# 从构建阶段复制安装的Python包
COPY --from=builder /install /usr/local

# 复制应用代码
COPY . /app

# 创建必要的目录
RUN mkdir -p /app/config && \
    chmod +x /app/entrypoint.sh && \
    rm -rf extra doc preview README.md LICENSE .gitignore

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 入口点
ENTRYPOINT ["/app/entrypoint.sh"]


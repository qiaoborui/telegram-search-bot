# 构建阶段：安装依赖和编译
FROM python:3.9-slim AS builder

# 设置工作目录
WORKDIR /build

# 安装构建依赖 - 添加更多必要的构建工具
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    postgresql-client \
    libpq-dev \
    python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 升级pip
RUN pip install --no-cache-dir --upgrade pip wheel setuptools

# 只复制requirements.txt以利用缓存
COPY requirements.txt .

# 预先安装psycopg2-binary，避免编译原生psycopg2
RUN pip install --no-cache-dir psycopg2-binary

# 安装Python依赖到指定目录，忽略已安装的psycopg2
RUN grep -v "psycopg2==" requirements.txt > requirements_filtered.txt && \
    pip install --no-cache-dir --prefix=/install -r requirements_filtered.txt

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

# 安装psycopg2-binary在最终镜像中
RUN pip install --no-cache-dir psycopg2-binary

# 复制应用代码 - 只复制必要的文件
COPY app/ /app/app/
COPY templates/ /app/templates/
COPY locale/ /app/locale/
COPY main.py webapp.py webapp_main.py entrypoint.sh /app/

# 创建必要的目录
RUN mkdir -p /app/config && \
    chmod +x /app/entrypoint.sh

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 入口点
ENTRYPOINT ["/app/entrypoint.sh"]


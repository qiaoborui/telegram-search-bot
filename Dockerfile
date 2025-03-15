FROM python:3.9-slim

WORKDIR /app

# 首先只安装系统依赖，这样只有在依赖变化时才会重新构建
RUN apt-get update && \
    apt-get install -y \
    gcc \
    postgresql-server-dev-all \
    libpq-dev \
    fonts-dejavu \
    fonts-noto-cjk \
    fonts-wqy-microhei \
    fonts-wqy-zenhei \
    fontconfig && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    fc-cache -f -v

# 列出可用字体，用于调试
RUN fc-list | grep -i "chinese\|cjk\|dejavu\|wqy"

# 更新pip并安装Python依赖
RUN /usr/local/bin/python -m pip install --upgrade pip

# 先只复制 requirements.txt，这样只有依赖变化时才会重新安装
COPY requirements.txt .
RUN pip install -r requirements.txt

# 最后才复制应用代码
ADD . /app
RUN rm -rf extra doc preview README.md LICENSE .gitignore

ENTRYPOINT ["/app/entrypoint.sh"]


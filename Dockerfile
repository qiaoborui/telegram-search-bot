FROM python:3.9-slim

WORKDIR /app

ADD . /app

RUN rm -rf extra doc preview README.md LICENSE .gitignore

# 安装系统依赖和字体
RUN apt update && \
    apt install -y gcc postgresql-server-dev-all libpq-dev \
    fonts-dejavu fonts-noto-cjk fonts-wqy-microhei fonts-wqy-zenhei \
    fontconfig && \
    apt clean && \
    fc-cache -f -v

# 更新pip并安装Python依赖
RUN /usr/local/bin/python -m pip install --upgrade pip
RUN pip install -r requirements.txt

# 列出可用字体，用于调试
RUN fc-list | grep -i "chinese\|cjk\|dejavu\|wqy"

ENTRYPOINT ["/app/entrypoint.sh"]


FROM python:3.9-slim

WORKDIR /app

ADD . /app

RUN rm -rf extra doc preview README.md LICENSE .gitignore

RUN apt update && apt install gcc postgresql-server-dev-all libpq-dev -y && apt clean
RUN /usr/local/bin/python -m pip install --upgrade pip
RUN pip install -r requirements.txt

ENTRYPOINT ["/app/entrypoint.sh"]


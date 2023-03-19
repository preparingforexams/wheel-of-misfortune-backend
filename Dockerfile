FROM python:3.11-slim

WORKDIR /app

ENV POETRY_VIRTUALENVS_CREATE=false

RUN pip install poetry==1.4.1 --no-cache

COPY [ "poetry.toml", "poetry.lock", "pyproject.toml", "./" ]
COPY src .

RUN poetry install --no-dev

ARG APP_VERSION
ENV APP_VERSION=$APP_VERSION

EXPOSE 8000

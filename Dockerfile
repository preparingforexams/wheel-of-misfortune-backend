FROM python:3.11-slim

WORKDIR /app

ENV POETRY_VIRTUALENVS_CREATE=false

RUN pip install poetry --no-cache

COPY [ "poetry.toml", "poetry.lock", "pyproject.toml", "./" ]
COPY src .

RUN poetry install --no-dev

EXPOSE 8000

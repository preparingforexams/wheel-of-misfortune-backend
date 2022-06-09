FROM python:3.10-slim

WORKDIR /app

RUN pip install poetry

COPY pyproject.toml .
COPY poetry.lock .
COPY src .

RUN poetry install --no-dev

EXPOSE 8000

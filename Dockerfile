FROM python:3.10-slim

WORKDIR /app

RUN pip install poetry --no-cache
RUN poetry config virtualenvs.create false

COPY [ "poetry.toml", "poetry.lock", "pyproject.toml", "./" ]
COPY src .

RUN poetry install --no-dev

EXPOSE 8000

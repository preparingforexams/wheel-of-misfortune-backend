FROM python:3.10-slim

WORKDIR /app

RUN pip install poetry

COPY pyproject.toml .
COPY poetry.lock .

RUN poetry install --no-dev

COPY main.py .

EXPOSE 8000

CMD poetry run uvicorn main:app --host 0.0.0.0

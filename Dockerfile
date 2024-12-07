FROM ghcr.io/blindfoldedsurgery/poetry:2.1.2-pipx-3.13-bookworm

COPY [ "poetry.toml", "poetry.lock", "pyproject.toml", "./" ]

RUN poetry install --no-interaction --ansi --only=main --no-root

# We don't want the tests
COPY src/misfortune ./src/misfortune

RUN poetry install --no-interaction --ansi --only-root

ARG APP_VERSION
ENV APP_VERSION=$APP_VERSION

EXPOSE 8000

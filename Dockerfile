FROM ghcr.io/blindfoldedsurgery/poetry:2.1.2-pipx-3.13-bookworm

COPY [ "poetry.toml", "poetry.lock", "pyproject.toml", "./" ]

RUN poetry install --no-interaction --ansi --only=main --no-root

# We don't want the tests
COPY src/misfortune ./src/misfortune

RUN poetry install --no-interaction --ansi --only-root

ARG APP_VERSION
ENV APP_VERSION=$APP_VERSION

EXPOSE 8000

FROM ghcr.io/astral-sh/uv:0.5-python3.13-bookworm-slim

RUN apt-get update -qq \
    && apt-get install -yq --no-install-recommends tini  \
    && apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

RUN groupadd --system --gid 500 app \
  && useradd --system --uid 500 --gid app --create-home --home-dir /app app

USER app
WORKDIR /app

COPY [ "uv.lock", "pyproject.toml", "./" ]

RUN uv sync --locked --no-install-workspace --all-extras --no-dev

# We don't want the tests
COPY src/misfortune ./src/misfortune

RUN uv sync --locked --no-editable --all-extras --no-dev

ARG APP_VERSION
ENV APP_VERSION=$APP_VERSION
ENV UV_NO_SYNC=true

EXPOSE 8000

ENTRYPOINT [ "tini", "--", "uv", "run" ]

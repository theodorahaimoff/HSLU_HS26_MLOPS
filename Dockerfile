# Feature pipeline image: pull SAKE, WEA and LIK, build the features, write a new version to the feature store.
#
#   docker build -t unemployment-features --build-arg GIT_COMMIT=$(git rev-parse HEAD) .
#   docker run --rm -v "$PWD/data/raw/exploration:/app/data/raw/exploration:ro" unemployment-features --offline
#                                     # offline: the snapshots of notebook 01 (gitignored, local only)
#   docker run --rm -e GCS_BUCKET=<bucket> \
#     -e GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/gcp-key.json \
#     -v "$PWD/gcp-key.json:/run/secrets/gcp-key.json:ro" unemployment-features
#
# No credentials in the image: the bucket name and the key are supplied at run time.

FROM python:3.14-slim

# uv, pinned to a version (not :latest), copied in from its official image
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Non-root user with a fixed uid/gid
RUN groupadd --gid 1001 app && useradd --uid 1001 --gid app --create-home app
WORKDIR /app
RUN chown app:app /app
USER app
# data/ must be writable by the app user for --offline runs (local store)
RUN mkdir -p /app/data/raw

# Dependencies first: this layer is only rebuilt when the lockfile changes.
# --locked fails the build if uv.lock and pyproject.toml disagree; --no-dev leaves out jupyter, pytest and ruff.
COPY --chown=app:app pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# Code last: it changes on every commit
COPY --chown=app:app src ./src

# Lets the manifest of every feature version name the commit that built it
ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=$GIT_COMMIT

# Exec form, so the process receives SIGTERM directly. Arguments after the image name are passed on (e.g. --offline).
ENTRYPOINT ["python", "-m", "src.feature_pipeline.run"]

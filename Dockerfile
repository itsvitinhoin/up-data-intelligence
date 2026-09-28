# Override with python:3.13-slim-bookworm@sha256:<digest> for a release build.
ARG PYTHON_BASE=python:3.13-slim-bookworm
FROM ${PYTHON_BASE}
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.lock ./
RUN python -m pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements.lock \
    && groupadd --gid 10001 worker \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin worker
COPY src ./src
COPY sql ./sql
COPY docs/upzero-openapi.json ./docs/upzero-openapi.json
USER 10001:10001
ENTRYPOINT ["python", "-m", "src.jobs.cli"]
CMD ["--help"]

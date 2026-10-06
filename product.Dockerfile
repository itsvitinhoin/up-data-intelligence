ARG PYTHON_BASE=python:3.13-slim-bookworm
FROM ${PYTHON_BASE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY product-requirements.lock ./
RUN python -m pip install --no-cache-dir --require-hashes --only-binary=:all: -r product-requirements.lock \
    && groupadd --gid 10001 product \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin product
# Build archives may use a private umask. Normalize application permissions
# explicitly: root owns the code; the non-root runtime can read, never write it.
COPY --chown=0:10001 src ./src
COPY --chown=0:10001 sql ./sql
RUN find src sql -type d -exec chmod 0750 {} + \
    && find src sql -type f -exec chmod 0640 {} +
USER 10001:10001
# Cloud Run explicitly selects read_app() or admin_app(). No ingestion entrypoint change.
ENTRYPOINT ["gunicorn"]
CMD ["--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "120", "--access-logfile", "/dev/null", "src.product_auth.runtime:read_app()"]

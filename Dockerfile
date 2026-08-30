# The API container: Django on uvicorn, for Azure Container Apps.
#
# Two stages, because `mysqlclient` is a C extension and publishes Windows-only
# wheels -- every Linux install builds it from source and needs a compiler and
# the MySQL client headers. Those belong in a build stage and not in the image
# that faces the internet.
#
# See design/conflict.md C31 for what this runs on and why.

FROM python:3.14-slim AS build

# `default-libmysqlclient-dev` is the MariaDB client library on Debian, which is
# what mysqlclient links against. Naming the driver's build dependencies here is
# the same list .env.example carries for a developer on Linux.
RUN apt-get update && apt-get install --no-install-recommends -y \
        build-essential \
        pkg-config \
        default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies before source, so a change to a Python file does not rebuild the
# wheel for every dependency underneath it.
COPY pyproject.toml poetry.lock* ./
RUN python -m venv /venv \
    && /venv/bin/pip install --no-cache-dir --upgrade pip poetry-plugin-export poetry \
    && /venv/bin/poetry export --without-hashes --format requirements.txt --output /tmp/requirements.txt \
    && /venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt


FROM python:3.14-slim AS runtime

# `libmariadb3` is the runtime half of the build dependency above -- the shared
# library mysqlclient loads. `ca-certificates` carries the DigiCert roots that
# Azure Database for MySQL chains to, which is what DJANGO_DB_SSL_CA points at.
RUN apt-get update && apt-get install --no-install-recommends -y \
        libmariadb3 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 f2c

COPY --from=build /venv /venv
ENV PATH="/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=f2c.settings

WORKDIR /app
COPY --chown=f2c:f2c . .

# Not root. Container Apps does not require it and an image that runs as root
# makes every later hardening decision harder than it needs to be.
USER f2c

EXPOSE 8000

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
CMD ["serve"]

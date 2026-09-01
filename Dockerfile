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

# The static tree, baked into the image rather than built at start-up. WhiteNoise
# serves STATIC_ROOT and nothing writes to it otherwise, so without this line the
# admin renders unstyled -- design/deploy.md 5.1.
#
# The two variables are throwaway and exist only so `f2c/settings.py` imports:
# it refuses to load without DJANGO_SECRET_KEY, and with DEBUG off it also
# requires every Payfast variable. Neither is read by `collectstatic`, neither
# is baked into the image (a RUN-line variable does not persist), and the key
# below is not the one the container runs with -- Container Apps supplies that.
#
# `--clear` because .dockerignore keeps staticfiles/ out of the build context
# today; if that ever changes, a developer's stale hashed files must not ship.
RUN DJANGO_DEBUG=1 \
    DJANGO_SECRET_KEY=build-only-never-used-at-runtime \
    python manage.py collectstatic --noinput --clear

EXPOSE 8000

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
CMD ["serve"]

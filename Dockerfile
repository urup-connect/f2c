# The API container: Django on uvicorn, for Azure Container Apps.
#
# **One image, three roles.** The same build is the API, the Celery worker and
# Celery beat -- `deploy/entrypoint.sh` picks between them from its first
# argument, and `CMD` below chooses the API. That is the whole reason the
# scheduler is Celery inside this application rather than a Function App or a
# Container Apps Job: no second deployment artefact, no second runtime, and the
# worker is guaranteed to be running the same code as the API that wrote the
# rows it acts on. See design/deploy.md 5.2.
#
# Two stages, because `mysqlclient` is a C extension and publishes Windows-only
# wheels -- every Linux install builds it from source and needs a compiler and
# the MySQL client headers. Those belong in a build stage and not in the image
# that faces the internet.
#
# See design/conflict.md C31 for what this runs on and why.

# **The base image is pinned by digest, and the tag beside it is there to be
# read rather than resolved.** design/deploy.md R-D7.
#
# This image is *promoted* between environments rather than rebuilt -- 6.4 --
# so what production runs is the artefact QA ran, whatever tag it came from,
# and R-D7 does not bite here the way it bites the two frontends. Pinned
# anyway, for the rebuild that does happen: a rebuild of an older commit, to
# reproduce a fault or to ship a fix on top of it, should produce the image
# that commit described and not the one `3.14-slim` happens to point at
# today.
#
# **One ARG rather than a digest on each FROM line.** A digest copied twice
# is a digest that can be bumped once, and a build stage on one Python with a
# runtime stage on another is a difference that surfaces as something else
# entirely.
#
# python:3.14-slim as at 2 September 2026, which is Python 3.14.7. To bump it, take
# the *top-level* digest -- the multi-platform index, not one platform's
# manifest:
#
#     docker buildx imagetools inspect python:3.14-slim
ARG PYTHON_IMAGE=python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6

FROM ${PYTHON_IMAGE} AS build

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


FROM ${PYTHON_IMAGE} AS runtime

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

# **STATIC_ROOT, created here as root and handed to `f2c` -- not left to
# `collectstatic` below to create.** It looks redundant, because the build does
# run `collectstatic` and that would create the directory anyway. What it buys
# is deterministic *ownership of a named volume*.
#
# `compose.yaml` mounts `api-staticfiles` over this path, and Docker initialises
# a new named volume by copying the image's directory at that path, ownership
# included. So with this line the volume root belongs to uid 10001 and the `dev`
# entrypoint can write it. Without a directory in the image to copy from, Docker
# creates the volume root owned by **root**, and `collectstatic` at container
# start fails as uid 10001 with:
#
#     PermissionError: [Errno 13] Permission denied: '/app/staticfiles'
#
# **A named volume is initialised once, on creation, and never again.** A volume
# that was created root-owned by an earlier image stays root-owned through every
# later `--build`, so this line cannot repair one that already exists. That is
# `docker compose down -v`, and it costs nothing here: the only thing in this
# volume is collectstatic output, rebuilt at every container start.
RUN mkdir -p /app/staticfiles && chown f2c:f2c /app/staticfiles

# Not root. Container Apps does not require it and an image that runs as root
# makes every later hardening decision harder than it needs to be.
USER f2c

# The static tree, baked into the image rather than built at start-up. WhiteNoise
# serves STATIC_ROOT and nothing writes to it otherwise, so without this line the
# admin renders unstyled -- design/deploy.md 5.1.
#
# The four variables are throwaway and exist only so `f2c/settings.py` imports.
# It refuses to load without DJANGO_SECRET_KEY, without both encryption keys,
# and -- with DEBUG off -- without every Payfast variable. None of the four is
# read by `collectstatic`, none is baked into the image (a RUN-line variable
# does not persist), and none is what the container runs with: Container Apps
# supplies those.
#
# **The two encryption keys were missing, and the image could not build.**
# `docker compose up --build` failed on this line naming both variables. The
# refusal in `settings.py` is unconditional -- there is no DEBUG exemption, and
# there should not be, because a backend that boots with encryption
# misconfigured writes plaintext or crashes at the first identity capture
# (design/backend.md section 3.3). `.dockerignore` keeps `.env` out of the build
# context, also correctly, so nothing here was supplying them. Fixed by giving
# the build its own throwaway pair -- the same trade DJANGO_SECRET_KEY above
# already takes -- rather than by weakening the refusal.
#
# Both are valid 32-byte base64, which is what `common/crypto.py` requires of
# the real ones, and both say what they are in plaintext when decoded. Fixed
# rather than generated per build: a value that changed every build would
# imply something read it.
#
# `--clear` because .dockerignore keeps staticfiles/ out of the build context
# today; if that ever changes, a developer's stale hashed files must not ship.
RUN DJANGO_DEBUG=1 \
    DJANGO_SECRET_KEY=build-only-never-used-at-runtime \
    DJANGO_FIELD_ENCRYPTION_KEY=ZmllbGQtZW5jcnlwdGlvbi1idWlsZC1vbmx5ISEhISE= \
    DJANGO_BLIND_INDEX_PEPPER=YmxpbmQtaW5kZXgtcGVwLWJ1aWxkLW9ubHkhISEhISE= \
    python manage.py collectstatic --noinput --clear

EXPOSE 8000

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
# The API. The worker and beat run this same image with `worker` and `beat`
# instead -- neither serves traffic, and beat must be capped at one replica.
CMD ["serve"]

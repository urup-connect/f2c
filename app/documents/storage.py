"""Where a revision's file is written, and the address it is served from.

Uploads go to the Azure Blob Storage container the CDN fronts, so a PDF uploaded
in the admin is live on the CDN without anyone copying it there by hand. Where no
container is configured -- local development, and the test suite -- they go to
``MEDIA_ROOT`` instead, so the feature works without credentials.

The backend is resolved through ``django.core.files.storage.storages`` rather
than instantiated here, and ``DocumentVersion.file`` is declared with a
reference to ``document_storage`` rather than a backend object. The reason is
migrations: ``FileField.deconstruct`` writes back the callable it was given, so
a migration records *"whatever the documents storage is"* rather than baking in
a backend path and a set of options that would then be frozen in history.

It is not laziness. Django calls a callable ``storage`` in ``FileField.__init__``,
so the backend is resolved as soon as the model is imported. With a container
configured, ``django-storages`` therefore has to be installed for Django to
start at all -- which is the right failure: an immediate, named one, rather than
an upload that works locally and dies in the admin.

``documents_storage_config`` is the reader that turns environment variables into
the ``STORAGES['documents']`` entry. It lives here rather than in settings, and
it is a pure function of an environment mapping, so every branch and every
refusal is testable without an Azure account or the package installed -- the same
shape as the frontend's configuration readers in ``lib/site.ts``.
"""
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import storages

# The key in settings.STORAGES. Deliberately not 'default': member uploads, if
# there are ever any, must not land in the container the CDN serves publicly.
DOCUMENTS_STORAGE_ALIAS = 'documents'

# Prefix for every blob written by this app, inside the container. Kept here
# rather than in settings so the layout is the same in every environment; the
# account, the container and the CDN host are what differ between environments,
# and those are configuration.
DOCUMENTS_PREFIX = 'documents'

FILESYSTEM_BACKEND = 'django.core.files.storage.FileSystemStorage'
AZURE_BACKEND = 'storages.backends.azure_storage.AzureStorage'

# A published revision's blob never changes -- the version is part of its name,
# so a revision is a new blob rather than an overwrite. That is what makes an
# immutable, effectively permanent cache header safe, and it is why nothing in
# front of this ever needs purging.
DOCUMENTS_CACHE_CONTROL = 'public, max-age=31536000, immutable'


def document_storage():
    """The backend revision files live on. Resolved per call, never cached."""
    return storages[DOCUMENTS_STORAGE_ALIAS]


def document_upload_to(instance, filename):
    """``documents/<document>/<version>/<file name>``.

    The version sits in the path rather than only in the file name, and that is
    the reason a CDN in front of this never needs purging: the address of a
    revision never changes, and a new revision has an address of its own. It
    also means an upload cannot overwrite the file a member has already agreed
    to, whatever it is called.

    The label is used as typed rather than slugified, because the model already
    constrains it to characters that are safe in a path -- and slugifying would
    quietly turn version ``2.1`` into ``21``.
    """
    return '/'.join(
        (
            DOCUMENTS_PREFIX,
            instance.document.slug,
            instance.label,
            PurePosixPath(filename).name,
        )
    )


def managed_identity_credential():
    """A ``DefaultAzureCredential``, imported only if it is actually needed.

    The credential App Service supplies to an app with a managed identity. No
    secret is involved, which is why it is the path this project prefers: an
    account key in application settings is a key that has to be rotated, copied
    between environments, and kept out of screenshots.
    """
    try:
        from azure.identity import DefaultAzureCredential
    except ImportError as error:
        raise ImproperlyConfigured(
            'No account key, SAS token or connection string is configured for '
            'DJANGO_DOCUMENT_STORAGE_CONTAINER, so the container is reached with '
            'a managed identity -- which needs the azure-identity package.\n'
            '    poetry add azure-identity\n'
            'Or set DJANGO_DOCUMENT_STORAGE_ACCOUNT_KEY to use an account key '
            'instead.'
        ) from error
    return DefaultAzureCredential()


def _custom_domain(cdn_base_url, container, *, debug):
    """The CDN host to serve blobs from, checked against the container.

    Azure blob URLs always carry the container as the first path segment, and
    django-storages replaces only the host when ``custom_domain`` is set. So a
    CDN base of ``https://host/consumer-collective`` and a container of
    ``consumer-collective`` describe the same address -- but a base whose path
    names something else describes an address that does not exist, and the
    symptom is every document link 404ing after a deploy. Refused here instead.
    """
    if not cdn_base_url:
        return None, True

    parts = urlsplit(cdn_base_url)

    if parts.scheme not in {'http', 'https'} or not parts.netloc:
        raise ImproperlyConfigured(
            f'DJANGO_CDN_BASE_URL is set to "{cdn_base_url}", which is not an '
            'absolute http or https URL.'
        )

    if parts.scheme != 'https' and not debug:
        raise ImproperlyConfigured(
            'DJANGO_CDN_BASE_URL must be https outside local development. The '
            'club documents are served from it, and a document fetched over '
            'plain http can be rewritten in transit.'
        )

    if parts.query or parts.fragment:
        raise ImproperlyConfigured(
            'DJANGO_CDN_BASE_URL carries a query or fragment. Give the scheme, '
            'the host and at most the container path.'
        )

    path = parts.path.strip('/')

    if path and path != container:
        raise ImproperlyConfigured(
            f'DJANGO_CDN_BASE_URL ends in "/{path}" but the container is '
            f'"{container}". An Azure blob URL always carries the container as '
            'its first path segment, so these have to agree -- otherwise every '
            'document link points at an address that does not exist. Either '
            f'rename the container to "{path}" or point the CDN base at '
            f'"/{container}".'
        )

    return parts.netloc, parts.scheme == 'https'


def documents_storage_config(env, *, debug=False, credential_factory=None):
    """The ``STORAGES['documents']`` entry, read from an environment mapping.

    Azure Blob Storage when a container is named, the local filesystem
    otherwise. The fallback is not a degraded mode to be apologised for: it is
    what lets the whole feature -- upload, digest, publish, serve -- be
    developed and tested with no cloud account at all.

    Credentials, in the order they are looked for:

    1. a connection string, which carries the account and the key together;
    2. an account name with an account key, or with a SAS token;
    3. a managed identity, when an account name is given and no secret is.

    Three is the one to use on App Service. It is last only because an
    explicitly configured secret should never be silently ignored in favour of
    an ambient identity -- if someone set a key, they meant it.
    """
    container = (env.get('DJANGO_DOCUMENT_STORAGE_CONTAINER') or '').strip()

    if not container:
        return {'BACKEND': FILESYSTEM_BACKEND}

    account = (env.get('DJANGO_DOCUMENT_STORAGE_ACCOUNT') or '').strip()
    account_key = (env.get('DJANGO_DOCUMENT_STORAGE_ACCOUNT_KEY') or '').strip()
    sas_token = (env.get('DJANGO_DOCUMENT_STORAGE_SAS_TOKEN') or '').strip()
    connection_string = (
        env.get('DJANGO_DOCUMENT_STORAGE_CONNECTION_STRING') or ''
    ).strip()
    location = (env.get('DJANGO_DOCUMENT_STORAGE_LOCATION') or '').strip('/')
    cdn_base_url = (env.get('DJANGO_CDN_BASE_URL') or '').strip().rstrip('/')

    if not account and not connection_string:
        raise ImproperlyConfigured(
            'DJANGO_DOCUMENT_STORAGE_CONTAINER is set, so the club documents go '
            'to Azure Blob Storage -- but neither '
            'DJANGO_DOCUMENT_STORAGE_ACCOUNT nor '
            'DJANGO_DOCUMENT_STORAGE_CONNECTION_STRING is set, so there is no '
            'account to write them to. Leave the container blank to store them '
            'on local disk instead.'
        )

    custom_domain, use_https = _custom_domain(cdn_base_url, container, debug=debug)

    options = {
        'azure_container': container,
        # A revision's blob must never be replaced: it is what a member's
        # agreement points at. The version is part of the name, so a new
        # revision is a new blob rather than an overwrite of an agreed one.
        'overwrite_files': False,
        # None means an unsigned URL. Explicit rather than left to the default,
        # because the alternative is a SAS token in every link -- and these
        # links go into a page anybody can open, and eventually into emails.
        'expiration_secs': None,
        'cache_control': DOCUMENTS_CACHE_CONTROL,
    }

    if location:
        options['location'] = location

    if connection_string:
        options['connection_string'] = connection_string
    else:
        options['account_name'] = account
        if account_key:
            options['account_key'] = account_key
        elif sas_token:
            options['sas_token'] = sas_token
        else:
            factory = credential_factory or managed_identity_credential
            options['token_credential'] = factory()

    if custom_domain:
        options['custom_domain'] = custom_domain
        # Whether the URLs this builds are https. Derived from the CDN base
        # rather than configured twice.
        options['azure_ssl'] = use_https

    return {'BACKEND': AZURE_BACKEND, 'OPTIONS': options}

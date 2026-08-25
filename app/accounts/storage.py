"""Where a member's avatar is written, and why it is never given a URL.

An avatar is the first thing a member uploads, and it is the reason this module
exists rather than the documents one being reused. ``documents.storage`` writes
to the container the CDN fronts, and says in as many words that member uploads
must not land there. That comment is now load-bearing: a club document is
published to everybody, and an avatar is a photograph of somebody's face.

So this is a **private** store, and nothing here ever calls ``.url()``. The
container has no public access and no SAS is minted, which means the only address
an avatar has is ``GET /api/accounts/me/avatar`` -- a Django view that checks the
session before it streams a byte. The cost is real and accepted: avatars are
served by the application rather than by a CDN, so they are slower and they cost
a request each. They are 512-pixel squares of a few tens of kilobytes, cached by
the browser, and a member looks at their own.

The duplication with ``documents.storage`` is deliberate. ``documents`` depends
on ``accounts``; an import the other way would make the two apps mutually
dependent, which is the one rule the app layout does not bend. If a third
uploading feature arrives, the credential resolution below is what to lift into
``common`` -- and at that point ``documents.storage`` moves with it.

``avatars_storage_config`` is a pure function of an environment mapping, the same
shape as its twin, so every branch and every refusal is testable without an Azure
account or the package installed.
"""
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import storages

# The key in settings.STORAGES. Not 'default', and not 'documents': an avatar
# must not be reachable from the container the CDN serves.
AVATARS_STORAGE_ALIAS = 'avatars'

# Prefix for every blob this app writes, inside the container. Here rather than
# in settings so the layout is identical in every environment; the account and
# the container are what differ, and those are configuration.
AVATARS_PREFIX = 'avatars'

FILESYSTEM_BACKEND = 'django.core.files.storage.FileSystemStorage'
AZURE_BACKEND = 'storages.backends.azure_storage.AzureStorage'


def avatar_storage():
    """The backend avatars live on. Resolved per call, never cached."""
    return storages[AVATARS_STORAGE_ALIAS]


def avatar_upload_to(instance, filename):
    """``avatars/<user id>/avatar.jpg``.

    One path per account, overwritten in place. That is the opposite of the
    documents rule, and for the opposite reason: a published revision is a thing
    a member agreed to and must never change, whereas an avatar has no history
    worth keeping and every replacement left behind would be a photograph of a
    face the club has no reason to still hold.

    The file name is discarded. What a member's phone called the image tells us
    nothing, may contain anything, and would otherwise reach a storage path.
    ``avatars.py`` guarantees the content is a JPEG, so the extension is stated
    here rather than inferred.
    """
    return '/'.join((AVATARS_PREFIX, str(instance.pk), 'avatar.jpg'))


def managed_identity_credential():
    """A ``DefaultAzureCredential``, imported only if it is actually needed.

    The credential App Service supplies to an app with a managed identity. No
    secret is involved, which is why it is the path this project prefers: an
    account key in application settings is a key that has to be rotated, copied
    between environments, and kept out of screenshots.

    The twin of ``documents.storage.managed_identity_credential``. See this
    module's docstring on why it is a twin rather than an import.
    """
    try:
        from azure.identity import DefaultAzureCredential
    except ImportError as error:
        raise ImproperlyConfigured(
            'No account key, SAS token or connection string is configured for '
            'DJANGO_AVATAR_STORAGE_CONTAINER, so the container is reached with '
            'a managed identity -- which needs the azure-identity package.\n'
            '    poetry add azure-identity\n'
            'Or set DJANGO_AVATAR_STORAGE_ACCOUNT_KEY to use an account key '
            'instead.'
        ) from error
    return DefaultAzureCredential()


def avatars_storage_config(env, *, credential_factory=None):
    """The ``STORAGES['avatars']`` entry, read from an environment mapping.

    Azure Blob Storage when a container is named, the local filesystem
    otherwise. The fallback is not a degraded mode to be apologised for: it is
    what lets the whole feature -- crop, upload, replace, serve -- be developed
    and tested with no cloud account at all.

    Credentials, in the order they are looked for, and the reasoning is the same
    as ``documents.storage.documents_storage_config``:

    1. a connection string, which carries the account and the key together;
    2. an account name with an account key, or with a SAS token;
    3. a managed identity, when an account name is given and no secret is.

    **No ``custom_domain``, and no CDN option at all.** That is the difference
    from the documents config and it is the whole point of a separate store:
    there is no address for a CDN to front, because an avatar is only ever
    streamed by the endpoint that checked the session first. A future edit that
    adds one here has made every member's photograph public, so there is
    deliberately no parameter to set.
    """
    container = (env.get('DJANGO_AVATAR_STORAGE_CONTAINER') or '').strip()

    if not container:
        return {'BACKEND': FILESYSTEM_BACKEND}

    account = (env.get('DJANGO_AVATAR_STORAGE_ACCOUNT') or '').strip()
    account_key = (env.get('DJANGO_AVATAR_STORAGE_ACCOUNT_KEY') or '').strip()
    sas_token = (env.get('DJANGO_AVATAR_STORAGE_SAS_TOKEN') or '').strip()
    connection_string = (
        env.get('DJANGO_AVATAR_STORAGE_CONNECTION_STRING') or ''
    ).strip()
    location = (env.get('DJANGO_AVATAR_STORAGE_LOCATION') or '').strip('/')

    if not account and not connection_string:
        raise ImproperlyConfigured(
            'DJANGO_AVATAR_STORAGE_CONTAINER is set, so member avatars go to '
            'Azure Blob Storage -- but neither DJANGO_AVATAR_STORAGE_ACCOUNT '
            'nor DJANGO_AVATAR_STORAGE_CONNECTION_STRING is set, so there is '
            'no account to write them to. Leave the container blank to store '
            'them on local disk instead.'
        )

    if container == (env.get('DJANGO_DOCUMENT_STORAGE_CONTAINER') or '').strip():
        raise ImproperlyConfigured(
            'DJANGO_AVATAR_STORAGE_CONTAINER and '
            'DJANGO_DOCUMENT_STORAGE_CONTAINER name the same container. The '
            'documents container is fronted by the CDN and serves unsigned, '
            'permanently cacheable URLs -- putting avatars in it would publish '
            "every member's photograph. Use a private container of its own."
        )

    options = {
        'azure_container': container,
        # The opposite of the documents rule: a member replacing their avatar
        # replaces the blob, because `avatar_upload_to` gives an account one
        # path and the old photograph is not something to keep.
        'overwrite_files': True,
        # None means an unsigned URL, which against a private container is an
        # address that does not work. Stated so the intent is on the record:
        # nothing calls `.url()` on this backend. See the module docstring.
        'expiration_secs': None,
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

    return {'BACKEND': AZURE_BACKEND, 'OPTIONS': options}

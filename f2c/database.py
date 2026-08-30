"""Which database this project talks to, read from an environment mapping.

SQLite unless told otherwise, MySQL when it is. The same shape as
``payments.gateway.payfast_config`` and the two storage readers: a pure function
of a mapping, so every branch and every refusal is testable without a database
server anywhere near it.

``DATABASES`` used to be four hardcoded lines pointing at ``db.sqlite3``, which
made the deployed backend unconfigurable and the MySQL half of
``design/backend.md`` section 8 untestable -- there was no way to point the suite
at the database QA and production actually run.

**SQLite is the fallback and not a degraded mode.** The whole suite runs on it,
it is what a developer gets with no configuration at all, and section 8.6 is
where the limits of that are recorded: it builds partial indexes, expression
indexes and check constraints, so a constraint test passing here says nothing
about whether MySQL built the rule.

Three things below are not obvious and all of them matter more than they look.

**``sql_mode`` is set explicitly, and set in full.** Section 8.4 requires
``STRICT_TRANS_TABLES`` -- without it an over-long decimal is silently truncated
rather than refused, which on a money column is the worst available outcome. The
trap is that ``init_command`` *replaces* the server's ``sql_mode`` rather than
adding to it, so setting only ``STRICT_TRANS_TABLES`` would quietly discard the
zero-date and division-by-zero protections MySQL 8 has on by default. The whole
set is therefore named.

**The test database is given an explicit charset and collation.** MySQL's
default collation is case- *and* accent-insensitive, which is a real
dev-versus-production difference (section 8.3) and the reason strain uniqueness
rides on a slug. Pinning it here means a CI run reproduces production's
comparison semantics rather than whatever the server was built with.

**Transport security is stated rather than inherited, and a deployment has to
say which it wants.** This is the same silent-degradation trap as the SQLite
fallback above, one layer down. Azure Database for MySQL Flexible Server runs
``require_secure_transport=ON``, and mysqlclient defaults to
``ssl_mode=PREFERRED`` -- so a connection with no TLS configuration at all comes
up *encrypted but unverified*, with no certificate check and no hostname check,
and reports success. Nothing in a log says so. Every identity number in this
database is one accepted certificate away from a man in the middle, so
:func:`tls_options` refuses to guess: name a CA bundle in ``DJANGO_DB_SSL_CA``
and get ``VERIFY_IDENTITY``, or set ``DJANGO_DB_SSL_DISABLED`` and own the
decision in writing. A deployed MySQL that says neither does not start.
"""
from django.core.exceptions import ImproperlyConfigured

#: MySQL 8's default ``sql_mode``, with ``STRICT_TRANS_TABLES`` guaranteed
#: present. Named in full because ``init_command`` replaces the server's value
#: instead of adding to it -- see the module docstring.
STRICT_SQL_MODE = ','.join((
    'ONLY_FULL_GROUP_BY',
    'STRICT_TRANS_TABLES',
    'NO_ZERO_IN_DATE',
    'NO_ZERO_DATE',
    'ERROR_FOR_DIVISION_BY_ZERO',
    'NO_ENGINE_SUBSTITUTION',
))

#: What QA and production run. ``common.checks`` refuses anything older than
#: 8.0.16 and refuses MariaDB outright; this is the version the schema is
#: developed against.
TARGET_MYSQL = '8.4'

SQLITE_BACKEND = 'django.db.backends.sqlite3'
MYSQL_BACKEND = 'django.db.backends.mysql'

#: The only ``ssl_mode`` that checks both the certificate chain and the
#: hostname. ``VERIFY_CA`` stops at the chain, so it accepts a perfectly valid
#: certificate issued for some other server -- which is most of the attack this
#: is here to prevent.
VERIFY_IDENTITY = 'VERIFY_IDENTITY'

#: What counts as "yes" in an environment variable, matching
#: ``payments.gateway.payfast_config``.
TRUE_VALUES = frozenset({'1', 'true', 'yes', 'on'})


def tls_options(env):
    """The ``OPTIONS`` entries that put a deployed MySQL connection on TLS.

    Called only from the MySQL branch, which is only reached in ``qa`` and
    ``prod`` -- development is SQLite and never gets here.

    There is no default. mysqlclient has one (``PREFERRED``), it silently
    downgrades to an unverified connection, and that is exactly the outcome
    this project cannot afford: see the module docstring. So the two spellings
    below are the only two, and a deployment that names neither is refused
    before it can connect.

    :param env: a mapping, normally ``os.environ``.
    :returns: ``{'ssl_mode': ..., 'ssl': {...}}``, or ``{}`` when verification
        has been deliberately turned off.
    """
    ca = (env.get('DJANGO_DB_SSL_CA') or '').strip()
    disabled = (
        env.get('DJANGO_DB_SSL_DISABLED') or ''
    ).strip().lower() in TRUE_VALUES

    if ca and disabled:
        raise ImproperlyConfigured(
            'DJANGO_DB_SSL_CA names a certificate authority and '
            'DJANGO_DB_SSL_DISABLED turns certificate verification off. They '
            'contradict each other, and guessing which one the deployment '
            'meant is how an unverified connection reaches production. Set '
            'one or the other.'
        )

    if ca:
        # `ssl` carries the bundle, `ssl_mode` decides what is done with it.
        # Passing the bundle alone would be the worst of both: the file is
        # read, PREFERRED still applies, and nothing is verified.
        return {'ssl_mode': VERIFY_IDENTITY, 'ssl': {'ca': ca}}

    if disabled:
        # A local or containerised MySQL with no certificate of its own -- CI,
        # and a developer reproducing a MySQL-only constraint failure. Written
        # as a disable rather than as the absence of a setting so that it reads
        # as a downgrade in whatever deployment template carries it.
        return {}

    raise ImproperlyConfigured(
        'A deployed MySQL connection needs DJANGO_DB_SSL_CA -- the path to the '
        'certificate authority bundle the server presents, which for Azure '
        'Database for MySQL is the DigiCert Global Root. Without it '
        'mysqlclient connects with ssl_mode=PREFERRED: encrypted, unverified, '
        'and indistinguishable from the real thing. If the server genuinely '
        'has no certificate -- CI against a MySQL container, a local server -- '
        'set DJANGO_DB_SSL_DISABLED=true and say so on purpose.'
    )


def database_config(env, base_dir):
    """The ``DATABASES['default']`` entry, read from an environment mapping.

    MySQL when ``DJANGO_DB_HOST`` names a server, SQLite otherwise. There is no
    ``DJANGO_DB_ENGINE=sqlite3`` spelling and no third option: this project runs
    on one database in development and one in deployment, and a general-purpose
    database URL parser would invite a fourth that nothing is tested against.

    :param env: a mapping, normally ``os.environ``.
    :param base_dir: the project root, for the SQLite file.
    """
    environment = (env.get('DJANGO_ENV') or 'dev').strip().lower()
    if environment in ('dev', 'test'):
        return {'ENGINE': SQLITE_BACKEND, 'NAME': base_dir / 'db.sqlite3'}
    if environment not in ('qa', 'prod'):
        raise ImproperlyConfigured(
            'DJANGO_ENV must be one of dev, test, qa, prod.'
        )

    host = (env.get('DJANGO_DB_HOST') or '').strip()

    if not host:
        # No host, no configuration, local disk. Named variables below are
        # ignored rather than half-applied, because a MySQL config missing its
        # host is a mistake and silently falling back to SQLite with a database
        # name set would hide it. That is what the refusal at the end is for.
        for named in ('DJANGO_DB_NAME', 'DJANGO_DB_USER'):
            if (env.get(named) or '').strip():
                raise ImproperlyConfigured(
                    f'{named} is set but DJANGO_DB_HOST is not, so this would '
                    'fall back to SQLite and ignore it. Set DJANGO_DB_HOST to '
                    f'use MySQL {TARGET_MYSQL}, or clear {named} to use the '
                    'local SQLite file.'
                )
        return {'ENGINE': SQLITE_BACKEND, 'NAME': base_dir / 'db.sqlite3'}

    name = (env.get('DJANGO_DB_NAME') or '').strip()
    user = (env.get('DJANGO_DB_USER') or '').strip()

    missing = [
        variable
        for variable, value in (('DJANGO_DB_NAME', name), ('DJANGO_DB_USER', user))
        if not value
    ]
    if missing:
        raise ImproperlyConfigured(
            f'DJANGO_DB_HOST is set, so this connects to MySQL -- but '
            f'{" and ".join(missing)} '
            f'{"is" if len(missing) == 1 else "are"} not set, so there is '
            'nothing to connect to. Clear DJANGO_DB_HOST to use the local '
            'SQLite file instead.'
        )

    return {
        'ENGINE': MYSQL_BACKEND,
        'NAME': name,
        'USER': user,
        # No refusal on a blank password. A local MySQL with a passwordless
        # user is a legitimate development setup, and refusing it here would be
        # this module inventing a policy the database itself is responsible for.
        'PASSWORD': env.get('DJANGO_DB_PASSWORD') or '',
        'HOST': host,
        'PORT': (env.get('DJANGO_DB_PORT') or '3306').strip(),
        'OPTIONS': {
            'charset': 'utf8mb4',
            'init_command': f"SET sql_mode='{STRICT_SQL_MODE}'",
            **tls_options(env),
        },
        'TEST': {
            'CHARSET': 'utf8mb4',
            # The 8.0+ default, pinned. See the module docstring.
            'COLLATION': 'utf8mb4_0900_ai_ci',
        },
    }

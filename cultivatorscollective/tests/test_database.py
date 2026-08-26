"""Which database the project connects to, and the refusals in between.

``database_config`` is a pure function of a mapping, so all of this runs with no
MySQL anywhere near it -- the same property that makes the storage and Payfast
readers testable, and for the same reason: the branches that matter are the ones
that refuse, and a refusal is the hardest thing to reach with real
infrastructure.

The test worth naming is ``test_a_named_database_with_no_host_is_refused``. The
quiet failure of this whole arrangement is a fallback to SQLite that nobody
notices: a typo in ``DJANGO_DB_HOST``, a variable renamed in a deployment
template, and the application comes up on a local file with every MySQL variable
set and ignored. On a developer's machine that is invisible; in CI it would make
the job that exists to prove the constraints pass for the wrong reason; in
production it is a member's data written somewhere nobody backs up. So a
half-configured MySQL is an error rather than a fallback, and the CI job asserts
``connection.vendor`` on top of it.
"""
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from ..database import (
    MYSQL_BACKEND,
    SQLITE_BACKEND,
    STRICT_SQL_MODE,
    database_config,
)

BASE_DIR = Path('/project')

MYSQL_ENV = {
    'DJANGO_DB_HOST': 'db.example.net',
    'DJANGO_DB_NAME': 'cultivatorscollective',
    'DJANGO_DB_USER': 'cultivators',
    'DJANGO_DB_PASSWORD': 'secret',
}


class SqliteTests(SimpleTestCase):
    def test_an_empty_environment_gives_the_local_file(self):
        """No configuration is a supported state, not a broken one."""
        config = database_config({}, BASE_DIR)

        self.assertEqual(config['ENGINE'], SQLITE_BACKEND)
        self.assertEqual(config['NAME'], BASE_DIR / 'db.sqlite3')

    def test_a_blank_host_gives_the_local_file(self):
        """A deployment template that renders an empty string is the same as one
        that renders nothing."""
        config = database_config({'DJANGO_DB_HOST': '   '}, BASE_DIR)

        self.assertEqual(config['ENGINE'], SQLITE_BACKEND)

    def test_a_named_database_with_no_host_is_refused(self):
        """The quiet failure. See the module docstring."""
        with self.assertRaises(ImproperlyConfigured) as refused:
            database_config({'DJANGO_DB_NAME': 'cultivatorscollective'}, BASE_DIR)

        self.assertIn('DJANGO_DB_HOST', str(refused.exception))

    def test_a_named_user_with_no_host_is_refused(self):
        with self.assertRaises(ImproperlyConfigured):
            database_config({'DJANGO_DB_USER': 'cultivators'}, BASE_DIR)

    def test_an_unrelated_variable_does_not_trigger_the_refusal(self):
        """Only the two that mean somebody intended MySQL. A stray password is
        harmless and refusing it would be this module inventing a rule."""
        config = database_config({'DJANGO_DB_PASSWORD': 'secret'}, BASE_DIR)

        self.assertEqual(config['ENGINE'], SQLITE_BACKEND)


class MysqlTests(SimpleTestCase):
    def config(self, **overrides):
        return database_config(MYSQL_ENV | overrides, BASE_DIR)

    def test_a_host_selects_mysql(self):
        config = self.config()

        self.assertEqual(config['ENGINE'], MYSQL_BACKEND)
        self.assertEqual(config['HOST'], 'db.example.net')
        self.assertEqual(config['NAME'], 'cultivatorscollective')
        self.assertEqual(config['USER'], 'cultivators')
        self.assertEqual(config['PASSWORD'], 'secret')

    def test_the_port_defaults_to_mysql_s_own(self):
        self.assertEqual(self.config()['PORT'], '3306')

    def test_a_port_is_honoured(self):
        self.assertEqual(self.config(DJANGO_DB_PORT='3307')['PORT'], '3307')

    def test_a_blank_password_is_allowed(self):
        """A passwordless local MySQL user is a legitimate development setup."""
        self.assertEqual(self.config(DJANGO_DB_PASSWORD='')['PASSWORD'], '')

    def test_a_missing_name_is_refused(self):
        with self.assertRaises(ImproperlyConfigured) as refused:
            self.config(DJANGO_DB_NAME='')

        self.assertIn('DJANGO_DB_NAME', str(refused.exception))

    def test_a_missing_user_is_refused(self):
        with self.assertRaises(ImproperlyConfigured) as refused:
            self.config(DJANGO_DB_USER='')

        self.assertIn('DJANGO_DB_USER', str(refused.exception))

    def test_the_refusal_names_everything_that_is_missing(self):
        """One run, not two. Somebody fixing a deployment should be told both."""
        with self.assertRaises(ImproperlyConfigured) as refused:
            self.config(DJANGO_DB_NAME='', DJANGO_DB_USER='')

        message = str(refused.exception)
        self.assertIn('DJANGO_DB_NAME', message)
        self.assertIn('DJANGO_DB_USER', message)

    def test_strict_mode_is_set_on_every_connection(self):
        """Without it an over-long decimal is truncated instead of refused, and
        that column is money. `design/backend.md` section 8.4."""
        init_command = self.config()['OPTIONS']['init_command']

        self.assertIn('STRICT_TRANS_TABLES', init_command)
        self.assertEqual(init_command, f"SET sql_mode='{STRICT_SQL_MODE}'")

    def test_strict_mode_keeps_the_servers_other_protections(self):
        """`init_command` REPLACES sql_mode rather than adding to it, so naming
        only STRICT_TRANS_TABLES would silently discard these."""
        for expected in (
            'NO_ZERO_DATE', 'NO_ZERO_IN_DATE', 'ERROR_FOR_DIVISION_BY_ZERO'
        ):
            with self.subTest(mode=expected):
                self.assertIn(expected, STRICT_SQL_MODE)

    def test_the_connection_is_utf8mb4(self):
        """Anything narrower fails mid-insert on an emoji rather than at
        validation."""
        self.assertEqual(self.config()['OPTIONS']['charset'], 'utf8mb4')

    def test_the_test_database_pins_charset_and_collation(self):
        """So a CI run reproduces production's comparison semantics. MySQL's
        default collation is case- and accent-insensitive, which is a real
        dev-versus-production difference -- section 8.3."""
        test = self.config()['TEST']

        self.assertEqual(test['CHARSET'], 'utf8mb4')
        self.assertEqual(test['COLLATION'], 'utf8mb4_0900_ai_ci')

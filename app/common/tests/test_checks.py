"""The database guards, exercised against fake connections.

``common.checks`` exists because Django omits a constraint the backend cannot
build without raising anything, which makes the database version a correctness
dependency of this codebase. A guard that is itself wrong is worse than no guard,
because it reads as reassurance -- so both are tested here, and tested against
made-up connections rather than a real MySQL.

That is deliberate. What is under test is *which database this application will
accept*, which is a decision expressed in Python, and it has to be assertable on
a developer's machine with SQLite and nothing else installed. A real MySQL would
test MySQL.
"""
from types import SimpleNamespace
from unittest import mock

from django.db import OperationalError, models
from django.test import TestCase

from .. import checks


class FakeConnection:
    display_name = 'MySQL'

    def __init__(self, *, vendor='mysql', version=(8, 4, 0), mariadb=False,
                 partial=True, expressions=True):
        self.vendor = vendor
        self.mysql_version = version
        self.mysql_is_mariadb = mariadb
        self.features = SimpleNamespace(
            supports_partial_indexes=partial,
            supports_expression_indexes=expressions,
        )


class _Unreachable:
    """A connection that raises the moment its version is asked for."""

    vendor = 'mysql'
    display_name = 'MySQL'
    features = SimpleNamespace(
        supports_partial_indexes=False, supports_expression_indexes=False
    )

    @property
    def mysql_is_mariadb(self):
        raise OperationalError('could not connect')

    @property
    def mysql_version(self):
        raise OperationalError('could not connect')


def run(check, connection):
    with mock.patch.object(checks, 'connections', {'default': connection}):
        return check(None, databases=['default'])


class VersionGuardTests(TestCase):
    check = staticmethod(checks.check_database_supports_the_schema)

    def test_the_target_version_is_accepted(self):
        self.assertEqual(run(self.check, FakeConnection(version=(8, 4, 0))), [])

    def test_the_minimum_version_is_accepted(self):
        """8.0.16 is where CHECK starts being enforced."""
        self.assertEqual(run(self.check, FakeConnection(version=(8, 0, 16))), [])

    def test_a_version_that_discards_check_constraints_is_refused(self):
        errors = run(self.check, FakeConnection(version=(8, 0, 15)))

        self.assertEqual([error.id for error in errors], ['common.E002'])
        self.assertIn('CHECK', errors[0].msg)

    def test_the_refusal_says_what_would_break(self):
        """A guard that only says no costs somebody an afternoon."""
        errors = run(self.check, FakeConnection(version=(5, 7, 0)))

        self.assertIn('is_active', errors[0].hint)
        self.assertIn('8.4', errors[0].hint)

    def test_mariadb_is_refused_at_any_version(self):
        errors = run(self.check, FakeConnection(version=(11, 4, 0), mariadb=True))

        self.assertEqual([error.id for error in errors], ['common.E001'])
        self.assertIn('expression index', errors[0].hint)

    def test_sqlite_is_left_alone(self):
        """Development. It builds everything this schema asks for."""
        self.assertEqual(run(self.check, FakeConnection(vendor='sqlite')), [])

    def test_an_unreachable_database_is_not_this_guard_s_business(self):
        """Django has its own check for that, and saying it twice helps nobody."""
        self.assertEqual(run(self.check, _Unreachable()), [])

    def test_no_databases_means_nothing_to_check(self):
        """`manage.py check` with no --database passes an empty list."""
        self.assertEqual(self.check(None, databases=[]), [])
        self.assertEqual(self.check(None), [])


class ConstraintShapeGuardTests(TestCase):
    """The more durable of the two guards: it reads the code, not the version.

    Someone adding a ``UniqueConstraint(condition=...)`` in six months gets told
    at ``migrate`` that it will not exist, rather than finding out when two
    members share a nickname.
    """

    check = staticmethod(checks.check_no_partial_or_expression_indexes_are_expected)

    def test_a_capable_backend_reports_nothing(self):
        self.assertEqual(run(self.check, FakeConnection()), [])

    def test_sqlite_reports_nothing(self):
        self.assertEqual(run(self.check, FakeConnection(vendor='sqlite')), [])

    def test_the_real_models_pass_on_a_backend_without_either_feature(self):
        """The assertion that matters. Every constraint in this project has to be
        one MySQL will actually build -- and nothing else in the suite can tell,
        because SQLite builds them all."""
        errors = run(
            self.check, FakeConnection(partial=False, expressions=False)
        )

        self.assertEqual(errors, [])

    def test_a_partial_unique_constraint_is_reported(self):
        with mock.patch(
            'django.apps.apps.get_models', return_value=[_ModelWithPartialIndex]
        ):
            errors = run(self.check, FakeConnection(partial=False))

        self.assertEqual([error.id for error in errors], ['common.E003'])
        self.assertIn('partial index', errors[0].msg)
        self.assertIn('nickname_key', errors[0].hint)

    def test_an_expression_unique_constraint_is_reported(self):
        with mock.patch(
            'django.apps.apps.get_models', return_value=[_ModelWithExpressionIndex]
        ):
            errors = run(self.check, FakeConnection(expressions=False))

        self.assertEqual([error.id for error in errors], ['common.E004'])
        self.assertIn('expression index', errors[0].msg)

    def test_a_check_constraint_is_never_reported(self):
        """Its `condition` is not a `WHERE` clause on an index, and MySQL 8.0.16
        builds it. Reporting one would make the guard cry wolf."""
        with mock.patch(
            'django.apps.apps.get_models', return_value=[_ModelWithCheckConstraint]
        ):
            errors = run(self.check, FakeConnection(partial=False, expressions=False))

        self.assertEqual(errors, [])


class _Meta:
    """Just enough of ``Options`` for the guard to walk."""

    def __init__(self, label, constraints):
        self.label = label
        self.constraints = constraints


class _ModelWithPartialIndex:
    _meta = _Meta(
        'fake.PartialIndex',
        [
            models.UniqueConstraint(
                fields=['name'],
                condition=~models.Q(name=''),
                name='fake_partial',
            )
        ],
    )


class _ModelWithExpressionIndex:
    _meta = _Meta(
        'fake.ExpressionIndex',
        [
            models.UniqueConstraint(
                models.functions.Lower('name'), name='fake_expression'
            )
        ],
    )


class _ModelWithCheckConstraint:
    _meta = _Meta(
        'fake.CheckConstraint',
        [
            models.CheckConstraint(
                condition=models.Q(name__gt=''), name='fake_check'
            )
        ],
    )

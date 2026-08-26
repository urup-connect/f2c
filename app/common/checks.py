"""A system check that refuses a database this application's schema needs more of.

``design/backend.md`` section 8 sets out what MySQL will and will not build, and
the reason this module exists is the last line of it: **Django omits a constraint
the backend cannot build without raising anything.** No error, no warning, no
line in the migration output. The model file, the migration and the test suite go
on describing a rule the deployed schema does not contain.

That makes the database version a correctness dependency of this codebase rather
than an operational detail, and an undeclared dependency is one that eventually
is not met. So it is declared here, and asserted before a migration runs.

Two things are checked.

**Check constraints have to be enforced.** Section 3.1's ``is_active`` backstop,
the role constraint, the sharing-member completeness rule and the catalogue's
price and percentage rules are all ``CHECK``. MySQL parses ``CHECK`` and
discards it before **8.0.16**, so on 8.0.15 every one of them is decoration and
a queryset ``.update()`` can write a member into a state the model says is
impossible.

**MariaDB is not a substitute.** It never builds expression indexes, whatever
its version. Nothing in this project depends on one *today* -- section 8.2's fix
moved the two that did onto plain columns -- but the difference is one Django
reports through the same silent omission, so a MariaDB deployment is a place
where the next such constraint disappears without a sound. It is refused rather
than warned about.

**Why this is a `database` check.** It opens a connection, so it must not run
during ``collectstatic`` or on a machine with no database reachable. Django only
runs ``Tags.database`` checks when they are asked for -- which ``migrate`` does,
and which is exactly the moment that matters, because a migration is where a
constraint would be silently skipped. ``manage.py check --database default``
runs it on demand.

A connection that cannot be reached is *not* an error here. Django has its own
check for that, and reporting the same fault twice in different words helps
nobody.
"""
from django.core.checks import Error, Tags, register
from django.db import OperationalError, connections, models

#: The first MySQL that enforces `CHECK` rather than parsing and discarding it.
#: Below this, every check constraint in the project is decoration.
MINIMUM_MYSQL = (8, 0, 16)

#: What QA and production actually run. Recorded so that the check can say
#: something useful about a version that is merely *old* rather than unusable --
#: 8.0.16 is the floor, and this is the target the schema is developed against.
TARGET_MYSQL = (8, 4)


def _version_text(version):
    return '.'.join(str(part) for part in version)


@register(Tags.database)
def check_database_supports_the_schema(app_configs, databases=None, **kwargs):
    """Refuse a database that would silently drop this project's constraints."""
    errors = []

    for alias in databases or ():
        connection = connections[alias]

        if connection.vendor != 'mysql':
            # SQLite in development, which supports partial indexes, expression
            # indexes and check constraints. Nothing to refuse -- and section 8.5
            # is where the fact that it is *not* the deployed database is
            # recorded, because a passing suite on SQLite proves nothing about
            # MySQL.
            continue

        try:
            is_mariadb = connection.mysql_is_mariadb
            version = connection.mysql_version
        except OperationalError:
            # Unreachable. Django's own database check reports that; saying it
            # again in different words helps nobody.
            continue

        if is_mariadb:
            errors.append(
                Error(
                    'MariaDB cannot build the indexes this schema relies on.',
                    hint=(
                        'MariaDB builds no expression index at any version, and '
                        'Django omits a constraint the backend cannot build '
                        'without raising anything -- so a constraint can be '
                        'absent from the deployed schema while the model, the '
                        'migration and the tests all still describe it. Use '
                        f'MySQL {_version_text(TARGET_MYSQL)}. See '
                        'design/backend.md section 8.'
                    ),
                    obj=alias,
                    id='common.E001',
                )
            )
            continue

        if version < MINIMUM_MYSQL:
            errors.append(
                Error(
                    f'MySQL {_version_text(version)} does not enforce CHECK '
                    'constraints, so this schema would be missing every one of '
                    'them.',
                    hint=(
                        f'MySQL enforces CHECK from {_version_text(MINIMUM_MYSQL)}; '
                        'before that it parses the clause and discards it. The '
                        'constraint keeping accounts.User.is_active in step with '
                        'status is one of them, so a queryset .update() could '
                        'lock a member out or let a suspended one back in with '
                        f'no error. Upgrade to MySQL {_version_text(TARGET_MYSQL)}. '
                        'See design/backend.md section 8.1.'
                    ),
                    obj=alias,
                    id='common.E002',
                )
            )

    return errors


@register(Tags.database)
def check_no_partial_or_expression_indexes_are_expected(
    app_configs, databases=None, **kwargs
):
    """Catch a constraint the backend will silently drop, before it is deployed.

    The guard above asserts the *version*. This one asserts the *code*, and it is
    the more durable of the two: it walks every model's constraints and reports
    any that this backend will omit rather than build.

    That closes the loop the whole of section 8 is about. Someone adding a
    ``UniqueConstraint(condition=...)`` in six months -- the natural, correct-
    looking spelling of a rule this project has needed three times already -- gets
    told at ``migrate`` that it will not exist, rather than finding out when two
    members share a nickname.
    """
    errors = []

    for alias in databases or ():
        connection = connections[alias]
        features = connection.features

        try:
            supports_partial = features.supports_partial_indexes
            supports_expressions = features.supports_expression_indexes
        except OperationalError:
            continue

        if supports_partial and supports_expressions:
            continue

        from django.apps import apps

        for model in apps.get_models():
            for constraint in model._meta.constraints:
                # `UniqueConstraint` only. A `CheckConstraint` also carries a
                # `condition`, and it is a different thing entirely -- not a
                # `WHERE` clause on an index but the rule itself, which MySQL
                # builds from 8.0.16. Treating the two alike made this guard
                # report every check constraint in the project, which is how a
                # guard stops being read.
                if not isinstance(constraint, models.UniqueConstraint):
                    continue

                condition = constraint.condition
                expressions = constraint.expressions
                label = f'{model._meta.label}.{constraint.name}'

                if condition is not None and not supports_partial:
                    errors.append(
                        Error(
                            f'{label} is a partial index, which '
                            f'{connection.display_name} cannot build.',
                            hint=(
                                'Django omits it silently, so the rule would be '
                                'absent from the deployed schema while the model '
                                'and the tests still describe it. Move the '
                                'condition into a derived column that is null '
                                'for the excluded rows and make the constraint '
                                'unconditional -- accounts.User.nickname_key is '
                                'the worked example. See design/backend.md '
                                'section 8.2.'
                            ),
                            obj=alias,
                            id='common.E003',
                        )
                    )

                if expressions and not supports_expressions:
                    errors.append(
                        Error(
                            f'{label} is an expression index, which '
                            f'{connection.display_name} cannot build.',
                            hint=(
                                'Django omits it silently. Store the computed '
                                'value in a column and constrain that instead -- '
                                'accounts.User.nickname_key is the worked '
                                'example. See design/backend.md section 8.2.'
                            ),
                            obj=alias,
                            id='common.E004',
                        )
                    )

    return errors

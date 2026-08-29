"""Resolving the producer both plant commands take as an argument.

Shared because the two commands must agree about it. The producer is the one
thing neither the template nor the upload may read from a file --
``spreadsheet``'s docstring says why -- so it arrives on the command line, and
"which farm is that" has to have exactly one answer.

**It resolves a producer, not a person.** It used to take an email address or a
nickname and return the `User` holding the cultivator role; stock belongs to the
farm, and a farm with three appointed staff had three equally good answers to
"who is the cultivator". A trading name has one.
"""
from django.core.management.base import CommandError

from app.commerce.producers.models import Producer


def resolve_cultivator(identifier):
    """The producer trading under this name.

    Matched case-insensitively against the derived key the uniqueness rule is
    built over, so the command and the database agree about what counts as the
    same name.
    """
    identifier = (identifier or '').strip()
    if not identifier:
        raise CommandError('Name a producer by its trading name.')

    producer = Producer.objects.filter(
        trading_name_key=identifier.lower()
    ).first()

    if producer is None:
        raise CommandError(
            f'No producer trades as {identifier!r}. Create it in the admin '
            'first -- stock belongs to a farm, not to the person keying it in.'
        )

    return producer

"""Resolving the cultivator both plant commands take as an argument.

Shared because the two commands must agree about it. The cultivator is the one
thing neither the template nor the upload may read from a file --
``spreadsheet``'s docstring says why -- so it arrives on the command line, and
"which account is that" has to have exactly one answer.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import CommandError

from app.accounts.roles import UserRole

User = get_user_model()


def resolve_cultivator(identifier):
    """The cultivator named by an email address or a nickname.

    Refuses an account that does not hold the cultivator role, because loading
    stock against a member's account creates inventory nobody can sell and a
    listing nobody owns. Refuses an erased account too: ``soft_delete`` keeps the
    role deliberately -- it is a fact about the club's structure rather than about
    the person -- so the role alone would still match one.
    """
    identifier = (identifier or '').strip()
    if not identifier:
        raise CommandError('Name a cultivator by email address or nickname.')

    if '@' in identifier:
        account = User.objects.filter(email=identifier.lower()).first()
    else:
        account = User.objects.by_nickname(identifier).first()

    if account is None:
        raise CommandError(f'No account matches {identifier!r}.')

    if account.deleted_at is not None:
        raise CommandError(
            f'{account.display_name} has been erased and cannot hold stock.'
        )

    if account.role != UserRole.CULTIVATOR:
        raise CommandError(
            f'{account.display_name} is not a cultivator. Appoint them in the '
            'admin first -- the role is what carries the authority to hold '
            'stock.'
        )

    return account

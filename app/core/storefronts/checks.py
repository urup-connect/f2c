"""System checks that keep the email configuration in step with the storefronts.

``MAILERS`` and ``STOREFRONT_FROM_EMAIL`` are keyed by storefront code, and
settings cannot import ``Storefront`` to get those codes -- that module is loaded
to *build* the app registry, so a models import there is a circular one. The two
lists are therefore written out twice, and this is what stops them drifting.

**Why it matters more than a typo usually does.** ``mail.mailer_for`` falls back
to the default storefront for anything it does not recognise, because a sign-in
must not fail on a mapping error. That fallback is right and it is also exactly
what would hide this: add a third storefront to ``Storefront`` without adding a
mailer, and its mail quietly leaves through the club's server, correctly
formatted, signed with the club's name. Nothing raises. Nobody notices until a
member asks why the club is emailing them about produce.

These are ordinary checks rather than ``Tags.database`` ones -- they read
settings and touch no connection, so they run on every ``manage.py`` command and
fail a deployment at startup rather than at the first send.
"""
from django.conf import settings
from django.core.checks import Error, register

from .models import Storefront


@register()
def check_every_storefront_can_send_email(app_configs, **kwargs):
    """Every storefront needs a mailer alias and a sender address of its own."""
    errors = []

    mailers = getattr(settings, 'MAILERS', None) or {}
    senders = getattr(settings, 'STOREFRONT_FROM_EMAIL', None) or {}

    for storefront in Storefront.values:
        if storefront not in mailers:
            errors.append(
                Error(
                    f'MAILERS has no {storefront!r} alias, so that storefront '
                    'cannot send email as itself.',
                    hint=(
                        'The MAILERS aliases are the storefront codes. Add one '
                        f'built from that storefront\'s EMAIL_*_ variables. '
                        'Without it, mail.mailer_for falls back to the default '
                        "storefront and the message leaves through another "
                        'storefront\'s server with no error at all. See the '
                        'Email block in f2c/settings.py.'
                    ),
                    id='storefronts.E001',
                )
            )

        if storefront not in senders:
            errors.append(
                Error(
                    f'STOREFRONT_FROM_EMAIL has no {storefront!r} entry.',
                    hint=(
                        'MAILERS carries no sender address, so this mapping is '
                        'what decides the From header. A missing entry falls '
                        'back to DEFAULT_FROM_EMAIL, which is a different '
                        "domain from at least one storefront's and will be "
                        'rejected by its provider.'
                    ),
                    id='storefronts.E002',
                )
            )

    return errors

"""The test runner, which exists for one reason: to stop the suite sending mail.

**Django's own isolation does not cover this project.**
``setup_test_environment()`` swaps ``settings.EMAIL_BACKEND`` for the locmem
backend and nothing else -- and nothing in this project sends through
``EMAIL_BACKEND``. Mail goes out per storefront, through ``MAILERS`` and
``EmailMessage.send(using=...)``, because the club and the market send as
different senders through different providers. See the MAILERS block in
``settings``.

So a developer with a populated ``.env`` had a suite pointed at
``EMAIL_CC_HOST``, a real mail server, and the only thing keeping it quiet was
that almost nothing sent outside a ``TestCase`` -- whose ``on_commit`` callbacks
never run. That stopped being true when suspending a membership started emailing
the member: ``test_models`` is a ``TransactionTestCase``, which *does* run them,
and the suite began opening TCP connections to port 465 and waiting out the
ten-second timeout on each.

Nothing was ever delivered -- the sends failed -- but a suite that tries is a
suite that can succeed, and mail from a test run reaches real addresses in the
fixtures. This makes it structural rather than a habit: every alias in
``MAILERS`` becomes locmem for the duration, so ``django.core.mail.outbox``
collects what any storefront sends and no host is contacted.
"""
from django.test.runner import DiscoverRunner

LOCMEM = 'django.core.mail.backends.locmem.EmailBackend'


class MailSafeRunner(DiscoverRunner):
    """``DiscoverRunner`` with every storefront mailer pointed at locmem."""

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)

        from django.conf import settings

        # Rebuilt rather than mutated in place: the aliases are what callers
        # pass to `send(using=...)`, so every one of them has to survive, and
        # only the backend behind each is replaced.
        self._real_mailers = settings.MAILERS
        settings.MAILERS = {
            alias: {'BACKEND': LOCMEM} for alias in self._real_mailers
        }

    def teardown_test_environment(self, **kwargs):
        from django.conf import settings

        settings.MAILERS = self._real_mailers
        super().teardown_test_environment(**kwargs)

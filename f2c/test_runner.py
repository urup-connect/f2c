"""The test runner, which holds what Django's own test environment does not
cover here: mail, the staticfiles backend, and a check that no test leaves a
settings override behind it.

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

**The staticfiles backend is the second.** ``STORAGES['staticfiles']`` is
WhiteNoise's ``CompressedManifestStaticFilesStorage``, which resolves every
``{% static %}`` through ``staticfiles.json`` and raises ``ValueError: Missing
staticfiles manifest entry`` when there is none. Django's runner turns ``DEBUG``
off, which is what makes that path strict, and nothing in a test run writes a
manifest -- so every test that renders an admin page would depend on whether
the developer had happened to run ``collectstatic``, and on nothing else.
Pinning the plain backend here keeps the suite about the templates.

Nothing is lost by that: the manifest path is exercised where it matters, in the
API image's build, where ``collectstatic`` runs and fails the build on an asset
that cannot be resolved.
"""
from django.test.runner import DiscoverRunner
from django.test.utils import override_settings

LOCMEM = 'django.core.mail.backends.locmem.EmailBackend'

#: Django's own, not WhiteNoise's manifest backend. See the module docstring.
PLAIN_STATICFILES = 'django.contrib.staticfiles.storage.StaticFilesStorage'


class MailSafeRunner(DiscoverRunner):
    """``DiscoverRunner`` with locmem mailers, plain staticfiles, and a leak check."""

    #: Set by `teardown_test_environment` when a settings override outlived the
    #: tests that enabled it. Read by `run_tests`, which turns it into a failure.
    _leaked = None

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

        # `override_settings` rather than an assignment, because
        # `staticfiles_storage` is a lazy object built once and rebuilt only on
        # the `setting_changed` signal -- which an assignment does not send.
        # Only the one alias is replaced; the others are whatever settings
        # configured, and the documents and avatars tests pin their own.
        self._staticfiles = override_settings(
            STORAGES={**settings.STORAGES,
                      'staticfiles': {'BACKEND': PLAIN_STATICFILES}}
        )
        self._staticfiles.enable()

        # What `settings._wrapped` has to be again once the tests are done:
        # every override enabled by a test is expected to put back the object it
        # replaced. Captured *after* the override above rather than before it,
        # because disabling that one restores this runner's own snapshot and
        # would paper over exactly the fault the check below is looking for.
        self._settings_expected = settings._wrapped

    def teardown_test_environment(self, **kwargs):
        from django.conf import settings

        # Checked before the override is disabled, for the reason given above.
        #
        # A settings override that outlived the tests that enabled it. This is
        # not theoretical and the suite has had one: `DocumentsTestCase`
        # disabled its override inside `tearDownClass`, while the one Django
        # enters for `@override_settings` on a subclass was still open and
        # unwound afterwards. Disabling out of order restores a snapshot taken
        # under the older override, so it comes back and stays -- and every
        # test that ran afterwards was reading a temporary MEDIA_ROOT and a
        # storages dict nobody had asked for.
        #
        # Nothing about that fails a test on its own. It changes what later
        # tests are testing, which is worse, so it fails the run here instead.
        if settings._wrapped is not self._settings_expected:
            # `UserSettingsHolder` keeps what an override set in its own
            # `__dict__`, alongside two bookkeeping attributes. Naming the
            # settings is most of the diagnosis, so they are worth digging out.
            held = getattr(settings._wrapped, '__dict__', {})
            self._leaked = sorted(
                name for name in held
                if name not in ('default_settings', '_deleted')
                and not name.startswith('__')
            )

        self._staticfiles.disable()
        settings.MAILERS = self._real_mailers
        super().teardown_test_environment(**kwargs)

    def run_tests(self, *args, **kwargs):
        failures = super().run_tests(*args, **kwargs)

        if self._leaked is not None:
            print()
            print('A settings override outlived the tests that enabled it: '
                  + (', '.join(self._leaked) or '(none named)'))
            print('Enable it with `cls.enterClassContext(override_settings(...))` '
                  'rather than a manual enable/disable pair, so it unwinds in '
                  'order with the ones Django enters for `@override_settings`.')
            failures += 1

        return failures

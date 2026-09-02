"""The test runner, which holds what Django's own test environment does not
cover here: mail, the task queue, the staticfiles backend, the host the test
client sends, and a check that no test leaves a settings override behind it.

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

**The task queue is the second.** CI runs with ``DJANGO_ENV=qa`` and a Redis
container, on purpose -- it is the only place the deployed cache backend is
exercised -- and the Celery broker is derived from that same URL. So in CI, and
for any developer with the compose stack up, ``CELERY_TASK_ALWAYS_EAGER`` is
*off*: a test that called a task would publish it to Redis, get an ``AsyncResult``
back, assert on a database that nothing had touched, and fail for a reason that
has nothing to do with the test. No worker is listening, and there should not be
one -- a suite that needs a second process running is a suite that fails
differently on every machine.

Eager is pinned here rather than in ``settings.py`` because it is a property of
running tests, not of an environment. Both halves are set: the Django setting,
for anything that reads it, and ``app.conf`` directly, because Celery loads its
configuration from settings once at finalisation and does not watch them
afterwards.

**Retries are pinned off, and that follows from eager rather than being a
second decision.** Every email is a task now, and ``storefronts.deliver_email``
retries a transport failure five times by default. Run eagerly those five
retries happen inline, immediately, with the countdown ignored -- so a test
that patches the mail backend to fail would hand over six times and then
surface whichever of Celery's eager-retry behaviours the installed version
has, instead of the failure it set up. Zero retries makes the first attempt
the last one, which is what a test asserting "a refused send is recorded as
failed" means. The retry logic itself is tested by overriding this back up,
in ``storefronts.tests.test_tasks``, where that is the subject.

**The staticfiles backend is the third.** ``STORAGES['staticfiles']`` is
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

**The test client's host is the fourth, and it is only noise.** Every request
the test client makes arrives as ``testserver``, which no deployment maps and
``DJANGO_STOREFRONT_HOSTS`` therefore never names. Django's runner turns
``DEBUG`` off, and with it off ``storefronts.resolution`` logs a warning on any
host it cannot map -- so a green run printed one line of "no storefront mapped
for host 'testserver'" per request and buried whatever else was in the log.
Mapping it to the club here says what the fallback already does, and leaves the
warning doing its job everywhere it means something: a deployed host that was
left out of the mapping.
"""
from django.test.runner import DiscoverRunner
from django.test.utils import override_settings

from app.core.storefronts.models import Storefront
from f2c.celery import app as celery_app

LOCMEM = 'django.core.mail.backends.locmem.EmailBackend'

#: Django's own, not WhiteNoise's manifest backend. See the module docstring.
PLAIN_STATICFILES = 'django.contrib.staticfiles.storage.StaticFilesStorage'


class MailSafeRunner(DiscoverRunner):
    """``DiscoverRunner`` with locmem mailers, eager tasks, plain staticfiles, a
    mapped test host, and a leak check."""

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

        # Tasks inline, with no broker and no worker. See the module docstring
        # for why this cannot live in `settings.py`: in CI the broker is real.
        #
        # `EMAIL_SEND_MAX_RETRIES=0` rides along with eager rather than being
        # its own switch, because it is the same fact: inline retries are
        # immediate, so five of them are five extra hand-overs between a test
        # and the failure it arranged. See the module docstring.
        self._eager = override_settings(
            CELERY_TASK_ALWAYS_EAGER=True,
            CELERY_TASK_EAGER_PROPAGATES=True,
            EMAIL_SEND_MAX_RETRIES=0,
        )
        self._eager.enable()

        # The same two on the app itself. Celery reads Django's settings once,
        # when it finalises, so the override above is invisible to it -- and
        # `app.conf` is what the task actually consults when it is called.
        self._real_eager = (
            celery_app.conf.task_always_eager,
            celery_app.conf.task_eager_propagates,
        )
        celery_app.conf.task_always_eager = True
        celery_app.conf.task_eager_propagates = True

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

        # `testserver` is the only host the test client ever sends, and no
        # deployment maps it. See the module docstring: without this every
        # request logs a warning meant for a misconfigured deployment. Mapped
        # to the club, which is where the unresolved fallback lands anyway, so
        # nothing about what is under test changes.
        self._storefront_hosts = override_settings(
            STOREFRONT_HOSTS={'testserver': Storefront.CLUB},
        )
        self._storefront_hosts.enable()

        # What `settings._wrapped` has to be again once the tests are done:
        # every override enabled by a test is expected to put back the object it
        # replaced. Captured *after* the overrides above rather than before
        # them, because disabling one of those restores this runner's own
        # snapshot and would paper over exactly the fault the check below is
        # looking for.
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

        self._storefront_hosts.disable()
        self._staticfiles.disable()
        (
            celery_app.conf.task_always_eager,
            celery_app.conf.task_eager_propagates,
        ) = self._real_eager
        self._eager.disable()
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

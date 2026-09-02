"""The Celery application, and the one place it is built.

Three jobs on this platform are computed rather than driven by an event, and
none of them runs itself -- ``lapse_memberships`` and the two retention purges.
This is what runs them, and :mod:`f2c.queue` carries the argument for why they
run here rather than in an Azure Function App or a Container Apps Job.

**Configuration is read from Django settings, not from this file.** Everything
below the app's construction is a wiring decision; every value is in
``settings.py`` under the ``CELERY_`` prefix, next to the prose explaining it
and inside the same review as the rest of the deployment's configuration. That
is what ``namespace='CELERY'`` buys: ``CELERY_TASK_ALWAYS_EAGER`` in settings is
``task_always_eager`` here, and there is no second configuration file to keep in
agreement with the first.

**``autodiscover_tasks`` is why no app has to register anything.** Each Django
app owning a scheduled job keeps its own ``tasks.py`` -- ``payments``,
``storefronts``, ``attribution`` -- and this finds them by walking
``INSTALLED_APPS``, which follows ``design/verticals.md`` section 7: an app owns
its models, its admin, its router and now its tasks. The names in
``CELERY_BEAT_SCHEDULE`` are the only place the schedule and the code meet.

**Nothing here is imported by hand.** ``f2c/__init__.py`` imports this module so
that the app exists before any ``@shared_task`` is called, which is what makes
``some_task.delay()`` work from inside a request. Losing that import does not
raise -- it changes ``shared_task`` from a task on this app into a task on no
app, and the failure surfaces later and elsewhere.
"""
import os

from celery import Celery

# Set before the app is constructed, because Celery's Django fixup reads it to
# call `django.setup()` in the worker -- which has no `manage.py` to do it. The
# `setdefault` matters: a `celery` command invoked with the variable already set
# is being pointed at a settings module on purpose.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'f2c.settings')

#: The application. `celery -A f2c worker` and `celery -A f2c beat` both resolve
#: to this object.
app = Celery('f2c')

# A lazy string rather than the settings object, so importing this module does
# not force Django's settings to load. `f2c/__init__.py` imports it at the top
# of the package, which is before `f2c.settings` has finished executing.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Deferred until the app is finalised, which is after the app registry is ready.
app.autodiscover_tasks()

"""The project package.

The import below is load-bearing and is the reason this file is not empty.
``@shared_task`` binds to whichever Celery app exists when the decorator runs,
so the app has to be built before any module carrying a task is imported --
which, in a Django process, is during ``INSTALLED_APPS`` population, long before
anything asks the queue for anything.

Removing it raises nothing. It turns every ``@shared_task`` into a task with no
app behind it, and the first symptom is a ``.delay()`` in a request path failing
somewhere else entirely. See ``f2c/celery.py``.
"""
from .celery import app as celery_app

__all__ = ['celery_app']

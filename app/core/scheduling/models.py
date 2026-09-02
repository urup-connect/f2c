"""What ran, when, and what it touched.

**A scheduled job with no record of its runs is a job nobody can prove ran.**
That is the gap this table closes, and it is the reason it exists at all rather
than the tasks simply logging. Three jobs run on a timer here and each one is
answerable to somebody:

* ``lapse_memberships`` withdraws a member's access. A member who says "I was
  switched off and I had paid" is asking a question about a specific run on a
  specific day, and the answer has to be readable by whoever takes that call --
  which means the admin, not a container log stream that has rolled over.
* the two purges **delete personal information** to satisfy POPIA's retention
  principle. A retention policy is only a policy if its enforcement is
  evidenced; "we delete send records after twelve months" is a claim, and a row
  per nightly run saying how many went is the thing that supports it under
  section 17's documentation duty.

So this is an operational audit trail, deliberately shaped as one.

**A row is written before the work starts, not after.** A job that dies
mid-flight -- a worker killed, a database that went away -- is exactly the case
an audit trail is for, and a record written on completion is a record that
misses it. What that costs is that ``RUNNING`` is an outcome the reader has to
interpret: fresh, it means a job in progress; hours old, it means a run that
never finished and nothing else will ever say so. That is information, and it is
the point.

**This table is written outside any transaction the job opens.** ``lapse_overdue``
commits per membership and the purges delete in one statement; if the record
shared a transaction with the work, a failed run would roll its own evidence
back and the table would only ever hold successes. See ``runs.record``.

**Nothing purges this table, and that is a decision.** Three rows a day is
roughly a thousand a year, carrying no personal information -- a task name, two
timestamps, a count. The retention argument that applies to the tables these
jobs delete from does not apply to the record that they ran, which is the
document POPIA's accountability principle wants kept. If it ever needs a window,
it needs its own setting and its own purge, not a share of either existing one.
"""
import uuid

from django.db import models

__all__ = ['Outcome', 'ScheduledRun', 'ScheduledTask']

#: How much of a failure is kept. The full traceback goes to the worker's log,
#: which is where a developer reads it; what belongs here is enough for an
#: operator to tell one failure from another at a glance and to quote it in a
#: ticket. A column that could hold a megabyte of traceback would be read by
#: nobody and backed up nightly.
DETAIL_LENGTH = 2000


class ScheduledTask(models.TextChoices):
    """The jobs that run on a timer.

    A registry, and the one place their names are written down. The values are
    the Celery task names in ``CELERY_BEAT_SCHEDULE``, so a schedule entry, a
    ``tasks.py`` and a row in this table all say the same string.

    **Not a check constraint, unlike every other known-values column in this
    project.** The constraint is the house pattern -- see
    ``campaign_touch_storefront_is_known`` -- and here it would be wrong. A
    fourth job whose author forgot to add it to this list would fail at the
    moment it wrote its own audit row, which is to say the retention purge would
    stop working because the record of the purge would not validate. The audit
    trail must never be the thing that breaks the job it is auditing, so an
    unregistered name is stored and shows as itself in the admin.
    """

    LAPSE_MEMBERSHIPS = (
        'payments.lapse_memberships',
        'Lapse memberships that have stopped paying',
    )
    PURGE_EMAIL_DISPATCHES = (
        'storefronts.purge_email_dispatches',
        'Purge send records past their retention window',
    )
    PURGE_CAMPAIGN_TOUCHES = (
        'attribution.purge_campaign_touches',
        'Purge campaign touches past their retention window',
    )


class Outcome(models.TextChoices):
    """How a run ended, or that it has not.

    ``RUNNING`` is written first and overwritten last, so it is both "in
    progress" and "never came back" -- told apart by ``started_at`` and nothing
    else. See the module docstring.
    """

    RUNNING = 'running', 'Running'
    SUCCEEDED = 'succeeded', 'Succeeded'
    FAILED = 'failed', 'Failed'


class ScheduledRunQuerySet(models.QuerySet):
    def for_task(self, task):
        """Runs of one job, newest first."""
        return self.filter(task=task).order_by('-started_at')

    def unfinished(self):
        """Runs still marked ``RUNNING``.

        The query behind "did last night's purge finish?". Past a job's own
        expected duration, every row here is a run that died without saying so.
        """
        return self.filter(outcome=Outcome.RUNNING)


class ScheduledRun(models.Model):
    """One execution of one scheduled job.

    Written by :func:`app.core.scheduling.runs.record`, which is what every
    task uses and the only thing that should create these.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)

    # Stored as the task name rather than as a foreign key to anything: the job
    # is code, it has no row of its own, and the name is what the schedule, the
    # worker's log and this table have in common.
    task = models.CharField(
        max_length=64,
        choices=ScheduledTask.choices,
        db_index=True,
        help_text='The scheduled job that ran.',
    )

    outcome = models.CharField(
        max_length=16,
        choices=Outcome.choices,
        default=Outcome.RUNNING,
        db_index=True,
        help_text=(
            'How the run ended. “Running” on an old row is a run that died '
            'without finishing.'
        ),
    )

    # Stamped by the database, like every other timestamp on this platform bar
    # `CampaignTouch.seen_at` -- two clocks for one fact eventually disagree.
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Empty while the run is in progress, and for a run that died.',
    )

    # What the run did, in the only unit the job has: memberships lapsed, send
    # records deleted, touches deleted. Zero is a real and common answer -- a
    # night on which nothing was overdue -- and is not the same as a run that
    # failed before it counted, which is what `outcome` is for.
    affected = models.PositiveIntegerField(
        default=0,
        help_text='How many rows the run changed or deleted.',
    )

    # `max_length` is deliberately not set. On a `TextField` Django enforces it
    # in forms only and the column is `longtext` regardless, so it would read as
    # a database limit that is not one. `runs.record` truncates to
    # `DETAIL_LENGTH` instead, which is where the decision is actually made.
    detail = models.TextField(
        blank=True,
        help_text=(
            'The failure, in one line. The full traceback is in the worker’s '
            'log. Blank for a run that succeeded.'
        ),
    )

    objects = ScheduledRunQuerySet.as_manager()

    class Meta:
        ordering = ('-started_at',)
        verbose_name = 'scheduled run'
        verbose_name_plural = 'scheduled runs'
        indexes = [
            # "When did this job last run, and did it work" -- the only question
            # this table is asked, and the only index it needs.
            models.Index(
                fields=['task', '-started_at'],
                name='scheduled_run_by_task',
            ),
        ]

    def __str__(self):
        return f'{self.get_task_display()} — {self.get_outcome_display().lower()}'

    @property
    def duration(self):
        """How long the run took, or ``None`` while it has not finished."""
        if self.finished_at is None:
            return None
        return self.finished_at - self.started_at

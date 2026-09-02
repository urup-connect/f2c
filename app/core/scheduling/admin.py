"""Reading the schedule's history, and never writing it.

This page answers one question -- *did the timer do its job?* -- and it is the
first place to look when a member says they were switched off unfairly or when
somebody has to evidence that a retention window is enforced rather than merely
declared.

**No add, no change, no delete.** A run either happened or it did not, and a
page that could edit the record of a deletion is a page that can make the
evidence say whatever is convenient. That is the same call
``CampaignTouchAdmin`` makes about editing a touch, taken one step further:
deleting is allowed there because a POPIA erasure request is sometimes answered
by hand, and there is no equivalent reason to remove a row from here. Nothing
in this table is personal information -- a task name, two timestamps and a
count -- so nobody can ask for it to be erased.

**What to look for.** Sort by started, filter by job. A row still showing
*Running* long after its slot is a run that died without reporting, and it is
the only failure mode the worker's own logs will not have shouted about.
"""
from django.contrib import admin

from .models import Outcome, ScheduledRun


@admin.register(ScheduledRun)
class ScheduledRunAdmin(admin.ModelAdmin):
    list_display = ('task', 'outcome', 'started_at', 'took', 'affected')
    # Outcome first: "has anything failed" is what this list is opened for.
    list_filter = ('outcome', 'task')
    ordering = ('-started_at',)
    date_hierarchy = 'started_at'
    search_fields = ('detail',)

    readonly_fields = (
        'id', 'task', 'outcome', 'started_at', 'finished_at', 'took',
        'affected', 'detail',
    )

    fieldsets = (
        (None, {'fields': ('id', 'task', 'outcome')}),
        ('Timing', {
            'fields': ('started_at', 'finished_at', 'took'),
            'description': (
                'The row is written before the work starts, so a run that was '
                'killed mid-flight is still here — with no finish time and '
                'still marked “running”. That is the only record such a run '
                'leaves anywhere.'
            ),
        }),
        ('Result', {
            'fields': ('affected', 'detail'),
            'description': (
                'How many rows the run changed or deleted. Zero is a real '
                'answer: a night on which nothing was overdue. The failure '
                'line is one line — the traceback is in the worker’s log.'
            ),
        }),
    )

    def has_add_permission(self, request):
        """No. A run is something that happened; it is not data to enter."""
        return False

    def has_change_permission(self, request, obj=None):
        """No, for anybody. See the module docstring."""
        return False

    def has_delete_permission(self, request, obj=None):
        """No. Nothing here is personal information, so nothing can be erased."""
        return False

    @admin.display(description='Took', ordering='finished_at')
    def took(self, obj):
        """The duration, or why there is not one.

        Ordered on ``finished_at`` rather than on the duration, which is not a
        column: the useful sort is "which runs have not come back", and the
        nulls carry that.
        """
        if obj.duration is None:
            return (
                '— still running' if obj.outcome == Outcome.RUNNING else '—'
            )
        seconds = obj.duration.total_seconds()
        return f'{seconds:.1f}s' if seconds < 60 else f'{seconds / 60:.1f}m'

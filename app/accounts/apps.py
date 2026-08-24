from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app.accounts'
    # What the admin sidebar calls this group. 'Accounts' reads as bookkeeping;
    # these are the people in the collective.
    verbose_name = 'Members'

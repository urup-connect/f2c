from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app.core.accounts'
    # Explicit, so the table names stay flat -- `accounts_user`, not
    # `core_accounts_user`. The apps moved under core/commerce/club in Block
    # 0.5; the label is what keeps that a package move rather than a rename
    # of every table, every migration dependency and `AUTH_USER_MODEL`.
    label = 'accounts'
    # What the admin sidebar calls this group. 'Accounts' reads as bookkeeping;
    # these are the people in the collective.
    verbose_name = 'Members'

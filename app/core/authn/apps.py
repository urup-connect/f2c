from django.apps import AppConfig


class AuthnConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app.core.authn'
    # Explicit, so the table names stay flat -- `accounts_user`, not
    # `core_accounts_user`. The apps moved under core/commerce/club in Block
    # 0.5; the label is what keeps that a package move rather than a rename
    # of every table, every migration dependency and `AUTH_USER_MODEL`.
    label = 'authn'
    # What the admin sidebar calls this group. Named for what staff come here
    # to do -- revoke a lost passkey, confirm a code was issued -- rather than
    # for the mechanism.
    verbose_name = 'Sign-in credentials'

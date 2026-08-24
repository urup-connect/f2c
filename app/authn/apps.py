from django.apps import AppConfig


class AuthnConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app.authn'
    # What the admin sidebar calls this group. Named for what staff come here
    # to do -- revoke a lost passkey, confirm a code was issued -- rather than
    # for the mechanism.
    verbose_name = 'Sign-in credentials'

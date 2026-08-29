from django.apps import AppConfig


class StorefrontsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app.core.storefronts'
    label = 'storefronts'
    # Two shopfronts on one platform, and who administers each. The storefront
    # itself is a column rather than a table -- see models.py.
    verbose_name = 'Storefronts'

    def ready(self):
        # Registers the guards in `checks.py`, which assert that the email
        # configuration in settings covers every storefront. Settings cannot
        # import `Storefront` to check that for itself -- see that module.
        from . import checks  # noqa: F401

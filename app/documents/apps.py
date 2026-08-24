from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app.documents'
    # What the admin sidebar calls this group. 'Documents' alone reads as file
    # management; these are the documents a member is bound by.
    verbose_name = 'Club documents'

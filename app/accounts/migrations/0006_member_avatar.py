"""The member's own photograph, and the stamp that lets a replacement be seen.

Two nullable columns and no data change: no account on file has a photograph,
and blank stays the normal state -- a member entitled to have no picture of
themselves on the club's record is not a gap to be backfilled.

``avatar`` is a ``FileField`` rather than an ``ImageField``. ``ImageField``
validates by decoding, which sounds like exactly what is wanted here and is not:
``accounts.avatars`` already decodes every upload and *re-encodes* it, so what
reaches this column is a 512-pixel JPEG this application produced. An
``ImageField`` would re-validate our own output on every full_clean and add
nothing, while implying the column would accept whatever an image library
happened to parse.

The ``storage`` argument is the callable ``accounts.storage.avatar_storage``
rather than a backend object, for the reason ``documents`` gives at greater
length: ``FileField.deconstruct`` writes back the callable it was given, so this
migration records *"whatever the avatars storage is"* rather than freezing a
backend path and a set of Azure options into history.

``avatar_updated_at`` exists because every avatar is written to the same path --
one per account, overwritten -- so the file name cannot tell a browser that the
picture changed. The stamp goes into the address the frontend requests, and a
replaced photograph is therefore fetched rather than served from cache.
"""
import app.accounts.storage
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_sharing_member'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='avatar',
            field=models.FileField(
                blank=True,
                help_text=(
                    'Set through the profile endpoint, which crops and re-encodes.'
                ),
                storage=app.accounts.storage.avatar_storage,
                upload_to=app.accounts.storage.avatar_upload_to,
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='avatar_updated_at',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
    ]

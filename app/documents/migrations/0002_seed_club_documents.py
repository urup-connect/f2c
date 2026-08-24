"""Register the three documents the sign-up form already asks about.

The identities only. No revisions, deliberately: the files currently on the CDN
predate this app, so nothing here knows their digests, and a seeded revision
would have to carry a blank ``sha256`` -- an unverifiable row in the one table
whose entire job is to be verifiable.

So sign-up fails closed until each document has a revision published through
the admin or through ``manage.py publish_club_document``. That is a deliberate
one-time step, and it is what gets a real digest recorded for every file a
member is ever shown.

The slugs match ``CLUB_DOCUMENT_IDS`` in the frontend, and the consent wording
matches what the form has been rendering. Both are seeds rather than
constraints: staff own them from here.
"""
from django.db import migrations

DOCUMENTS = [
    ('club-rules', 'Club Rules', 0, 'I have read and agree to the Club Rules'),
    ('annexures', 'Annexures', 1, 'I have read and agree to the Annexures'),
    ('constitution', 'Constitution', 2, 'I have read and agree to the Constitution'),
]


def seed(apps, schema_editor):
    ClubDocument = apps.get_model('documents', 'ClubDocument')
    for slug, title, position, _consent_text in DOCUMENTS:
        ClubDocument.objects.update_or_create(
            slug=slug,
            defaults={
                'title': title,
                'position': position,
                'required_at_signup': True,
            },
        )


def unseed(apps, schema_editor):
    """Remove the three rows, but never one that has a revision.

    A document with revisions has agreements pointing through it, and the
    foreign keys are PROTECT for that reason. Reversing this migration on a
    database that has been used is not something to force through.
    """
    ClubDocument = apps.get_model('documents', 'ClubDocument')
    slugs = [slug for slug, *_ in DOCUMENTS]
    ClubDocument.objects.filter(slug__in=slugs, versions__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('documents', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]

"""Upload and publish a document revision from the command line.

The admin is the normal route. This exists for the initial load, where three
PDFs that already live on the CDN have to be brought under version control at
once, and for a deployment pipeline that would rather not click.

It does exactly what the admin does, through the same model methods, so a
revision created here is indistinguishable from one created by hand -- digests
included.
"""
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from app.core.documents.models import Document, DocumentVersion
from app.core.storefronts.models import Storefront


class Command(BaseCommand):
    help = 'Upload a document revision and, unless told otherwise, publish it.'

    def add_arguments(self, parser):
        parser.add_argument(
            'document', help='Slug of an existing document on that storefront, e.g. constitution'
        )
        # Required, with no default. A slug is only unique within a storefront
        # now, so "publish terms v2" is an ambiguous instruction and defaulting
        # it would resolve the ambiguity silently -- onto whichever storefront
        # happened to be first in the enum.
        parser.add_argument(
            '--storefront',
            required=True,
            choices=[value for value, _ in Storefront.choices],
            help='Which storefront the document belongs to.',
        )
        parser.add_argument('version', help='Version label for this revision, e.g. 2')
        parser.add_argument('file', help='Path to the PDF to upload')
        parser.add_argument(
            '--consent-text',
            required=True,
            help=(
                'The exact sentence a member ticks, e.g. "I have read and agree '
                'to the Constitution".'
            ),
        )
        parser.add_argument(
            '--material',
            action='store_true',
            help=(
                'The change is material: members who agreed to an earlier '
                'revision will be asked again.'
            ),
        )
        parser.add_argument('--note', default='', help='Staff-facing change note.')
        parser.add_argument(
            '--draft',
            action='store_true',
            help='Upload without publishing. Nothing is offered to members.',
        )

    def handle(self, *args, **options):
        storefront = options['storefront']
        try:
            document = Document.objects.get(
                slug=options['document'], storefront=storefront
            )
        except Document.DoesNotExist:
            known = ', '.join(
                Document.objects.filter(storefront=storefront)
                .values_list('slug', flat=True)
            )
            raise CommandError(
                f'No {storefront} document with slug "{options["document"]}". '
                f'Known: {known or "none"}'
            )

        path = Path(options['file'])
        if not path.is_file():
            raise CommandError(f'{path} is not a file.')

        version = DocumentVersion(
            document=document,
            label=options['version'],
            consent_text=options['consent_text'],
            change_note=options['note'],
            requires_reacceptance=options['material'],
        )
        # full_clean before the upload, so a bad version label is caught before
        # bytes are pushed to the CDN.
        try:
            version.full_clean(exclude=['file', 'sha256', 'consent_text_sha256'])
        except ValidationError as error:
            raise CommandError('; '.join(error.messages))

        with path.open('rb') as handle:
            version.file.save(path.name, File(handle), save=False)
            version.save()

        self.stdout.write(
            f'Uploaded {version} as {version.file.name} '
            f'({version.byte_size} bytes, sha256 {version.sha256}).'
        )

        if options['draft']:
            self.stdout.write(
                self.style.WARNING(
                    'Left as a draft. Publish it in the admin, or run again '
                    'without --draft, before members can agree to it.'
                )
            )
            return

        try:
            version.publish()
        except ValidationError as error:
            raise CommandError('; '.join(error.messages))

        self.stdout.write(
            self.style.SUCCESS(
                f'Published {version}, in force from {version.effective_from:%Y-%m-%d %H:%M}. '
                f'Address: {version.url}'
            )
        )

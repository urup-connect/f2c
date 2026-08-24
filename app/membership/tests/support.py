"""Scaffolding for the registration tests.

Two things here rather than in the tests themselves.

``sa_id_for`` builds a structurally valid RSA ID number for a given date of
birth, check digit included. The suite needs several -- one per member, one
under age, one for the duplicate case -- and hard-coding them would mean a test
about *being under age* that actually fails on a check digit, which is the most
misleading way for a test to be green or red.

``RegistrationTestCase`` inherits the club-document scaffolding, because a
registration cannot happen without a published revision of every required
document. That is the point of ``DocumentsNotReady``, and it means every test
here has to publish three of them first.
"""
from datetime import date

from app.common.validators import luhn_is_valid
from app.documents.tests.support import DocumentsTestCase

#: The slugs migration 0002 seeds, in form order.
REQUIRED_DOCUMENTS = ('club-rules', 'annexures', 'constitution')


def sa_id_for(born, sequence='5009', citizenship='0'):
    """A well-formed RSA ID number encoding ``born``.

    ``YYMMDD SSSS C A Z``: date of birth, the sequence, the citizenship digit,
    the legacy digit, and a Luhn check digit computed here so the result passes
    ``validate_sa_id_number``.
    """
    body = f'{born:%y%m%d}{sequence}{citizenship}8'
    for candidate in '0123456789':
        if luhn_is_valid(body + candidate):
            return body + candidate
    raise AssertionError(f'No check digit completes {body}')


#: A member comfortably over eighteen, and a second identity for the tests that
#: need two people.
ADULT_BORN = date(1990, 3, 15)
ADULT_ID = sa_id_for(ADULT_BORN)
SECOND_ADULT_ID = sa_id_for(date(1985, 7, 2), sequence='5123')


class RegistrationTestCase(DocumentsTestCase):
    """A published revision of all three documents, and a valid submission."""

    def setUp(self):
        super().setUp()
        self.revisions = {
            slug: self.published(document=self.document(slug=slug), label='1')
            for slug in REQUIRED_DOCUMENTS
        }

    def consents(self, **overrides):
        """The three agreements, at the revisions actually in force."""
        submitted = [
            {'document': slug, 'version': self.revisions[slug].label}
            for slug in REQUIRED_DOCUMENTS
        ]
        for entry in submitted:
            if entry['document'] in overrides:
                entry['version'] = overrides[entry['document']]
        return submitted

    def submission(self, **overrides):
        """A submission every rule accepts, before ``overrides`` are applied."""
        payload = {
            'first_name': 'Thandiwe',
            'last_name': 'Mokoena',
            'nickname': 'Grower',
            'email': 'thandiwe@example.com',
            'mobile': '082 123 4567',
            'id_number': ADULT_ID,
            'consents': self.consents(),
        }
        payload.update(overrides)
        return payload

    def supersede(self, slug, label='2'):
        """Publish a newer revision of ``slug``, making the form's one stale.

        The file has to differ: ``publish`` refuses a byte-identical re-upload,
        because accepting one would ask every member to agree again to a
        document that did not change.

        ``effective_from`` is left as ``publish`` stamps it. ``published()``
        breaks a tie on the primary key, so this revision is the one in force
        even if both stamps land in the same microsecond.
        """
        return self.published(
            document=self.document(slug=slug),
            label=label,
            content=b'%PDF-1.7\na later revision\n%%EOF\n',
        )

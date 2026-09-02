"""Tests for creating a store customer.

Two halves, and the split is the one ``membership`` draws. The service tests
cover **what is written** -- one row, Active, and no relationship of any kind.
The endpoint tests cover **the contract**: which status code, which
machine-readable refusal, and what never appears in a response.

Three of these exist because the feature's whole value is what it does *not* do,
and none of those would fail on a wrong answer that merely looked plausible:

* ``GrantsNothingTests`` -- a customer holds no ``ClubMembership``, no
  ``StorefrontStaff``, no ``ProducerMembership`` and no permission. A
  registration that quietly created one would hand a shopper standing in a
  cannabis club, and every screen would look correct.
* ``DisclosureTests`` -- the response for an address already on file is
  **byte-identical** to the response for a new one. Asserted on the bytes rather
  than on the parsed body, because that is the property that matters.
* ``ConsentGuardTests`` -- publishing a market document at
  ``agreement=at_registration`` stops registration dead. Without it that
  publication would silently begin creating customers recorded as having agreed
  to nothing.
"""
import json
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.utils import timezone

from app.club.membership.models import ClubMembership
from app.commerce.producers.models import ProducerMembership
from app.core.accounts import registration
from app.core.accounts.models import User, UserStatus
from app.core.documents.models import Agreement, Audience, Document
from app.core.storefronts.models import (
    EmailDispatch,
    Storefront,
    StorefrontStaff,
)

REGISTER = '/api/customers/register'

DETAILS = {
    'first_name': 'Thandiwe',
    'last_name': 'Mokoena',
    'email': 'thandiwe@example.com',
    'mobile': '082 123 4567',
}


def submission(**overrides):
    return {**DETAILS, **overrides}


class RegistrationTestCase(TestCase):
    """Shared setup, and it deletes the club's seeded documents from nothing.

    The migration seeds three **club** documents at ``agreement=at_registration``
    and this endpoint is scoped to the market, so they are left exactly where
    they are: a test that removed them would stop covering the one thing
    ``StorefrontScopeTests`` exists to prove.
    """

    def register(self, **overrides):
        return registration.register_customer(**submission(**overrides))


class CreatesAnAccountTests(RegistrationTestCase):
    def test_it_creates_the_customer(self):
        outcome = self.register()

        self.assertTrue(outcome.created)
        customer = User.objects.get(email='thandiwe@example.com')
        self.assertEqual(outcome.user, customer)
        self.assertEqual(customer.first_name, 'Thandiwe')
        self.assertEqual(customer.last_name, 'Mokoena')

    def test_the_account_is_active(self):
        """Active, not pending anything.

        The club leaves a registrant's *membership* at pending payment; there is
        no membership here, so there is no second status to be pending in. This
        is the market vertical in one assertion.
        """
        self.register()

        customer = User.objects.get(email='thandiwe@example.com')
        self.assertEqual(customer.status, UserStatus.ACTIVE)
        self.assertEqual(customer.status, registration.REGISTERED_STATUS)
        self.assertTrue(customer.is_active)

    def test_it_normalises_what_was_typed(self):
        self.register(
            first_name='  Thandiwe   Nomsa ',
            email='THANDIWE@Example.COM ',
            mobile='0821234567',
        )

        customer = User.objects.get(email='thandiwe@example.com')
        self.assertEqual(customer.first_name, 'Thandiwe Nomsa')
        self.assertEqual(customer.mobile, '+27821234567')

    def test_the_customer_holds_no_password(self):
        """Nobody on this platform does. An unusable password cannot be guessed."""
        self.register()

        customer = User.objects.get(email='thandiwe@example.com')
        self.assertFalse(customer.has_usable_password())

    def test_a_blank_mobile_number_is_accepted(self):
        """It is what a driver rings, so a wrong number is worse than none."""
        outcome = self.register(mobile='')

        self.assertTrue(outcome.created)
        self.assertEqual(outcome.user.mobile, '')

    def test_two_customers_may_both_leave_the_mobile_blank(self):
        """`mobile_key` is null when the number is blank, and nulls are distinct.

        Written because the alternative -- a unique index over `mobile` itself --
        would let exactly one customer in the store decline to give a number.
        """
        self.register(mobile='')
        self.register(email='second@example.com', mobile='')

        self.assertEqual(User.objects.filter(mobile='').count(), 2)

    def test_no_identity_number_is_collected(self):
        self.register()

        customer = User.objects.get(email='thandiwe@example.com')
        self.assertFalse(customer.has_id_number)
        self.assertIsNone(customer.date_of_birth)


class GrantsNothingTests(RegistrationTestCase):
    """A customer is a ``User`` with no row in any of the other three.

    ``design/verticals.md`` section 6. This is the promise the market vertical
    rests on: authority resolves from three relationships, so a registration
    that created one would grant a shopper standing they never asked for and no
    screen would look wrong.
    """

    def setUp(self):
        super().setUp()
        self.register()
        self.customer = User.objects.get(email='thandiwe@example.com')

    def test_there_is_no_club_membership(self):
        self.assertFalse(
            ClubMembership.objects.filter(user=self.customer).exists()
        )

    def test_there_is_no_storefront_appointment(self):
        self.assertFalse(
            StorefrontStaff.objects.filter(user=self.customer).exists()
        )

    def test_there_is_no_producer_appointment(self):
        self.assertFalse(
            ProducerMembership.objects.filter(user=self.customer).exists()
        )

    def test_the_customer_holds_no_permissions_at_all(self):
        self.assertEqual(self.customer.get_all_permissions(), set())

    def test_the_customer_is_not_staff(self):
        self.assertFalse(self.customer.is_staff)
        self.assertFalse(self.customer.is_superuser)

    def test_the_customer_has_no_club_nickname(self):
        self.assertEqual(self.customer.club_nickname, '')

    def test_only_one_row_was_written(self):
        self.assertEqual(User.objects.count(), 1)


class DuplicateTests(RegistrationTestCase):
    """An address or a handset already on file writes nothing and says nothing.

    The service's answer differs from a success in exactly one respect, and it
    is not visible to whoever submitted the form: who gets emailed a code.
    """

    def test_a_repeated_address_writes_nothing(self):
        self.register()
        outcome = self.register(mobile='083 999 8888')

        self.assertFalse(outcome.created)
        self.assertIsNone(outcome.user)
        self.assertEqual(User.objects.count(), 1)

    def test_a_repeated_address_still_gets_a_sign_in_code(self):
        """The confirmation screen sends everybody to enter a code.

        Without this, a customer who forgot they had an account is told to wait
        for something that never arrives.
        """
        first = self.register()
        outcome = self.register()

        self.assertFalse(outcome.created)
        self.assertEqual(outcome.sign_in_for, first.user)

    def test_a_repeated_handset_writes_nothing(self):
        self.register()
        outcome = self.register(email='someone.else@example.com')

        self.assertFalse(outcome.created)
        self.assertEqual(User.objects.count(), 1)

    def test_a_repeated_handset_under_another_address_gets_no_code(self):
        """Emailing it would tell the typed address about somebody else's account."""
        self.register()
        outcome = self.register(email='someone.else@example.com')

        self.assertIsNone(outcome.sign_in_for)

    def test_a_handset_written_differently_is_still_the_same_handset(self):
        self.register(mobile='082 123 4567')
        outcome = self.register(email='other@example.com', mobile='+27821234567')

        self.assertFalse(outcome.created)

    def test_a_suspended_account_is_a_duplicate_and_gets_no_code(self):
        """A code would be an invitation to nothing: they cannot sign in."""
        first = self.register()
        first.user.deactivate()

        outcome = self.register()

        self.assertFalse(outcome.created)
        self.assertIsNone(outcome.sign_in_for)

    def test_an_erased_account_does_not_block_a_new_registration(self):
        """``soft_delete`` nulls the address, so it is free again.

        The same reason ``email_hash`` is not unique, and the reason
        ``has_been_seen`` is the wrong question here.
        """
        first = self.register()
        first.user.soft_delete()

        outcome = self.register()

        self.assertTrue(outcome.created)
        self.assertEqual(User.objects.count(), 2)


class RefusalTests(RegistrationTestCase):
    """Every field is checked here, not only in the browser.

    The endpoint is unauthenticated and reachable without the store at all.
    """

    def refusals(self, **overrides):
        with self.assertRaises(ValidationError) as raised:
            self.register(**overrides)
        return raised.exception

    def test_a_missing_name_is_refused(self):
        error = self.refusals(first_name='   ')

        self.assertIn('first_name', error.error_dict)
        self.assertEqual(User.objects.count(), 0)

    def test_a_malformed_address_is_refused(self):
        error = self.refusals(email='not-an-address')

        self.assertIn('email', error.error_dict)

    def test_a_number_that_is_not_a_mobile_is_refused(self):
        error = self.refusals(mobile='021 555 1234')

        self.assertIn('mobile', error.error_dict)

    def test_every_bad_field_is_reported_at_once(self):
        """Somebody with three things wrong is told three things once.

        ``membership`` raises on the first because its caller joins the
        messages into a sentence; the store renders a refusal under each input.
        """
        error = self.refusals(first_name='', email='nope', mobile='12345')

        self.assertEqual(
            set(error.error_dict), {'first_name', 'email', 'mobile'}
        )

    def test_the_validator_codes_survive(self):
        """The codes are what ``registration_api`` maps onto the wire.

        Asserted here as well as at the endpoint, because a validator that
        stopped setting ``code`` would leave the endpoint silently sending an
        empty ``fields`` and the store showing nothing wrong with the form.
        """
        error = self.refusals(first_name='', email='nope')

        self.assertEqual(
            [refusal.code for refusal in error.error_dict['first_name']],
            ['name_missing'],
        )
        self.assertEqual(
            [refusal.code for refusal in error.error_dict['email']],
            ['email_malformed'],
        )

    def test_nothing_is_written_when_any_field_is_refused(self):
        self.refusals(email='nope')

        self.assertEqual(User.objects.count(), 0)


class ConsentGuardTests(RegistrationTestCase):
    """Publishing a market document at registration stops this dead.

    The guard exists because that publication is one action in the Django admin,
    taken by whoever writes the terms rather than by whoever writes the
    endpoint -- and without it, it would quietly begin creating customers
    recorded as having agreed to nothing.
    """

    def market_document(self, **overrides):
        return Document.objects.create(
            **{
                'storefront': Storefront.MARKET,
                'slug': 'terms',
                'title': 'Terms of use',
                'audience': Audience.CUSTOMER,
                'agreement': Agreement.AT_REGISTRATION,
                **overrides,
            }
        )

    def test_registration_is_refused(self):
        self.market_document()

        with self.assertRaises(registration.ConsentRequired) as raised:
            self.register()

        self.assertEqual(raised.exception.slugs, ['terms'])
        self.assertEqual(User.objects.count(), 0)

    def test_a_document_needing_no_agreement_does_not_block_it(self):
        """A privacy notice is published, not agreed to. It must not stop sign-up."""
        self.market_document(slug='privacy-notice', agreement=Agreement.NONE)

        outcome = self.register()

        self.assertTrue(outcome.created)

    def test_a_retired_document_does_not_block_it(self):
        self.market_document(retired_at=timezone.now())

        outcome = self.register()

        self.assertTrue(outcome.created)

    def test_it_is_refused_even_with_no_published_revision(self):
        """A document with no revision cannot be agreed to either.

        Unlike ``/documents/current``, where the two states differ because
        sign-up has a form to render, both are the same refusal here.
        """
        self.market_document()

        with self.assertRaises(registration.ConsentRequired):
            self.register()


class StorefrontScopeTests(RegistrationTestCase):
    """The club's own documents must not refuse the store.

    The migration seeds three club documents at ``agreement=at_registration``,
    and every unmapped host -- every development machine, every preview
    deployment -- resolves to the club. A host-scoped guard would 503 the store
    everywhere but production.
    """

    def test_the_club_seeds_do_not_block_a_store_registration(self):
        self.assertTrue(
            Document.objects.agreed_at_registration(Storefront.CLUB).exists(),
            'the club seed is what this test is about; it has gone missing',
        )

        outcome = self.register()

        self.assertTrue(outcome.created)

    def test_the_guard_reads_the_market(self):
        self.assertEqual(registration.REGISTERS_INTO, Storefront.MARKET)


# ----------------------------------------------------------------------
# The endpoint
# ----------------------------------------------------------------------


class EndpointTestCase(TestCase):
    def setUp(self):
        super().setUp()
        # Limits live in the cache and are keyed on client IP, so without this
        # they carry from one test into the next and fail whichever ran last.
        cache.clear()
        self.client = Client()
        mail.outbox = []

    def post(self, **overrides):
        """POST a registration, and then let the request commit.

        The sign-in code is published from ``transaction.on_commit`` --
        ``storefronts.mail`` says why -- and a ``TestCase`` never commits,
        so without this the outbox stays empty and every test about the
        code fails on an empty list. See ``f2c.testing.flush_commit_hooks``.
        """
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                REGISTER,
                data=json.dumps(submission(**overrides)),
                content_type='application/json',
            )

    def body(self, response):
        return json.loads(response.content)


class EndpointTests(EndpointTestCase):
    def test_a_valid_submission_is_accepted(self):
        response = self.post()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 1)

    def test_the_response_carries_nothing_about_the_customer(self):
        """No id, no address, no name.

        The store answers this from a server action which then redirects, and a
        redirect carries only a URL -- so a response body with a value in it is
        a value in reach of a query string. ``membership`` states the rule and
        then has to break it for a checkout token; there is no payment here, so
        this one keeps it whole.
        """
        response = self.post()

        self.assertEqual(set(self.body(response)), {'detail'})
        content = response.content.decode()
        self.assertNotIn('thandiwe', content.lower())
        self.assertNotIn('Mokoena', content)
        self.assertNotIn('821234567', content)

    def test_it_emails_a_sign_in_code(self):
        """The confirmation screen promises one. This is what keeps that true."""
        self.post()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['thandiwe@example.com'])

    def test_a_mobile_number_may_be_omitted_entirely(self):
        """Absent, not blank. The store's form leaves the field optional, so a
        submission without it is complete rather than partial."""
        response = self.client.post(
            REGISTER,
            data=json.dumps(
                {
                    'first_name': 'Thandiwe',
                    'last_name': 'Mokoena',
                    'email': 'thandiwe@example.com',
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.get().mobile, '')


class DisclosureTests(EndpointTestCase):
    """Sign-up must not be a way of asking who shops here."""

    def test_a_duplicate_gets_the_identical_response(self):
        first = self.post()
        second = self.post()

        self.assertEqual(second.status_code, first.status_code)
        self.assertEqual(second.content, first.content)

    def test_a_duplicate_writes_nothing(self):
        self.post()
        self.post()

        self.assertEqual(User.objects.count(), 1)

    def test_a_suspended_account_answers_the_same_and_is_sent_nothing(self):
        first = self.post()
        User.objects.get().deactivate()
        mail.outbox = []

        second = self.post()

        self.assertEqual(second.content, first.content)
        self.assertEqual(mail.outbox, [])


class RefusalContractTests(EndpointTestCase):
    def test_a_bad_field_is_422_with_the_store_s_own_code(self):
        response = self.post(email='not-an-address')

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            self.body(response)['fields'], {'email': ['email-malformed']}
        )

    def test_every_bad_field_is_keyed_separately(self):
        response = self.post(first_name='', email='nope', mobile='12345')

        fields = self.body(response)['fields']
        self.assertEqual(
            fields,
            {
                'first_name': ['name-missing'],
                'email': ['email-malformed'],
                'mobile': ['mobile-not-a-mobile'],
            },
        )

    def test_the_codes_are_the_ones_the_store_renders(self):
        """The store drops any code it does not know, and shows a blank form.

        This is the contract test for that: every value this endpoint can emit
        has to be in the store's ``SIGN_UP_REFUSALS`` list. The list is
        duplicated here rather than read from TypeScript, and it is the smaller
        evil -- the alternative is a Python test parsing a ``.ts`` file.
        """
        rendered = {
            'name-missing',
            'name-too-long',
            'name-unexpected-characters',
            'email-missing',
            'email-malformed',
            'email-too-long',
            'mobile-unexpected-characters',
            'mobile-length',
            'mobile-not-a-mobile',
        }

        from app.core.accounts.registration_api import REFUSAL_CODES

        self.assertLessEqual(set(REFUSAL_CODES.values()), rendered)

    def test_a_refusal_carries_a_sentence_too(self):
        response = self.post(email='not-an-address')

        self.assertTrue(self.body(response)['detail'].strip())

    def test_a_refusal_sends_no_mail(self):
        self.post(email='not-an-address')

        self.assertEqual(mail.outbox, [])


class EndpointConsentGuardTests(EndpointTestCase):
    def test_it_answers_503(self):
        """Not 422 and not 500. Nothing is wrong with the submission and nothing
        is broken; the fix is a deployment rather than a retry."""
        Document.objects.create(
            storefront=Storefront.MARKET,
            slug='terms',
            title='Terms of use',
            audience=Audience.CUSTOMER,
            agreement=Agreement.AT_REGISTRATION,
        )

        response = self.post()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(mail.outbox, [])


class UndeliverableCodeTests(EndpointTestCase):
    """The account is written and the sign-in code does not arrive.

    **Found by running the endpoint against a real mail server that was not
    answering, not by reasoning about it.** It used to answer 503 here, and
    these tests were what pinned that down: a failed send during registration
    follows a row that has already committed, so letting the exception through
    would answer 500 to somebody whose account exists, and every retry would do
    it again because the retry is a duplicate and the duplicate path emails too.

    **The queue changed the answer, and the tests below are what that change
    looks like.** The mail server is no longer on this request path -- the code
    is recorded and published to a worker -- so an unreachable SMTP host is not
    something this endpoint can find out about. It answers 200, the row says
    ``failed``, and the worker will have retried before it settled there.

    That is a better outcome and it is not a free one, so it is worth being
    exact about what was given up. **Before:** the customer was told plainly
    that sign-up could not complete, and told it immediately. **Now:** the
    customer is told to check their email, and if the outage outlasts the
    retries, nothing arrives and nothing says why. What was bought is that a
    mail server which is merely slow, or briefly down, no longer fails a
    registration at all -- the code arrives late instead of never, and the
    account is usable when it does.

    **503 has not gone; it has narrowed.** It is still the answer when the code
    cannot be *recorded or queued* -- an unreachable database or broker -- which
    is the case where nothing will retry because nothing was written. See
    ``BrokerOutageTests`` below and ``registration_api.register``.
    """

    def failing_mail(self):
        """A mail backend that will not send.

        Patched at the backend itself, which is where the fault actually is in
        production: an unreachable SMTP host. It used to be patched a layer up,
        inside ``otp``, because ``_send`` was a ``sync_to_async`` wrapper built
        at import time and patching the function behind it left the wrapper
        pointing at the original -- the test passed while sending perfectly well,
        and only two of these six noticed. That hazard is gone: ``otp._send`` is
        an ordinary coroutine now.

        Patching here rather than in ``otp`` also keeps ``storefronts.mail`` in
        the path, so the send is recorded as failed on the way through and this
        exercises the whole of what a failed sign-in code does.
        """
        return mock.patch(
            'django.core.mail.EmailMessage.send',
            side_effect=OSError('mail server is not answering'),
        )

    def test_it_answers_200_and_records_the_failure(self):
        """**The change, asserted in one place.**

        The endpoint cannot know: it queued the message and returned. What
        knows is the row, which is the only thing that ever knew reliably --
        the 503 covered a hand-over refused synchronously and said nothing
        about one refused a second later.
        """
        with self.failing_mail():
            response = self.post()

        self.assertEqual(response.status_code, 200)
        dispatch = EmailDispatch.objects.get()
        self.assertEqual(EmailDispatch.SendStatus.FAILED, dispatch.send_status)
        self.assertIn('not answering', dispatch.send_error)

    def test_the_reply_is_the_one_a_working_send_gets(self):
        """Byte for byte. A customer must not be able to tell a mail outage
        from a working send, because the reply says nothing about either --
        it says to go and check an inbox."""
        with self.failing_mail():
            broken = self.post()
        User.objects.all().delete()
        EmailDispatch.objects.all().delete()

        working = self.post()

        self.assertEqual(broken.content, working.content)

    def test_the_account_is_kept(self):
        """Not rolled back to match the refusal.

        It is a good row and the failure is a mail server; undoing it would mean
        a second write that can fail for the same reason, and a customer whose
        next attempt starts from nothing.
        """
        with self.failing_mail():
            self.post()

        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(User.objects.get().status, UserStatus.ACTIVE)

    def test_the_kept_account_still_grants_nothing(self):
        with self.failing_mail():
            self.post()

        self.assertEqual(User.objects.get().get_all_permissions(), set())

    def test_a_retry_answers_the_same_thing(self):
        """And queues a second code, which is what the duplicate path is for.

        The retry writes no account -- the address is on file -- but it does
        send, because the confirmation screen sends everybody to the sign-in
        screen to enter a code. Two rows, two failures, one account.
        """
        with self.failing_mail():
            first = self.post()
            second = self.post()

        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.content, first.content)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(2, EmailDispatch.objects.failed().count())

    def test_it_says_nothing_about_whether_the_address_was_new(self):
        """The disclosure rule has to survive a mail outage.

        A refusal worded about the account rather than about the code would tell
        the second caller that the first one had already registered.
        """
        with self.failing_mail():
            fresh = self.post()
            duplicate = self.post()

        self.assertEqual(fresh.content, duplicate.content)

    def test_the_code_arrives_once_mail_works_again(self):
        """The recovery path, and the account written during the outage is the
        one the working code belongs to."""
        with self.failing_mail():
            self.post()
        mail.outbox = []

        response = self.post()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(1, EmailDispatch.objects.filter(
            send_status=EmailDispatch.SendStatus.SENT
        ).count())


class BrokerOutageTests(EndpointTestCase):
    """**Where the 503 went.**

    A mail server that will not answer is no longer this endpoint's problem --
    ``UndeliverableCodeTests`` says why. A broker that will not answer still
    is, and it is the more serious of the two: nothing was queued, so nothing
    will retry, and the customer holds an account with no way to sign in to it
    and no reason to expect one.

    503 is the same answer for the same reason it always was. The submission is
    fine, the account is kept, and the customer can only come back.
    """

    def unreachable_broker(self):
        """Publishing fails, as it does with Redis down.

        **Patched at ``mail._enqueue_in_thread`` and not at
        ``deliver_email.delay``, and the difference is the whole reason this
        class needed thinking about.** ``mail`` publishes from
        ``transaction.on_commit``. In production nothing here is inside a
        transaction, so Django runs that callback immediately and a broker
        failure raises inside the request -- which is what makes 503
        reachable. Under ``TestCase`` the surrounding transaction defers the
        callback to ``captureOnCommitCallbacks``, which is *after* the
        response, so patching ``delay`` produces a 200 and an exception in
        the test helper: a shape production does not have.

        Patching the coroutine that ``asend_storefront_email`` awaits puts
        the failure back where the request can see it. It is the same fault
        one call further out, and it is the only place a test inside a
        transaction can put it honestly.
        """
        async def refuse(*args, **kwargs):
            raise OSError('Error 111 connecting to redis:6379')

        return mock.patch(
            'app.core.storefronts.mail._enqueue_in_thread', refuse
        )

    def test_it_answers_503(self):
        with self.unreachable_broker():
            response = self.post()

        self.assertEqual(response.status_code, 503)

    def test_the_account_is_kept(self):
        """As it is for a mail outage, and for the same reason: it is a good
        row, and undoing it would leave the customer starting from nothing."""
        with self.unreachable_broker():
            self.post()

        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(User.objects.get().status, UserStatus.ACTIVE)

    def test_the_row_is_left_saying_it_was_never_handed_over(self):
        """``queued``, not ``failed``. Nothing refused this message -- nothing
        was ever asked -- and ``pending()`` is the query that finds it.

        The row survives the 503 because it is written before the publish is
        attempted, which is the same ordering that makes a send recorded
        before it is tried. A 503 with no row would leave an operator with
        nothing but a log line.
        """
        with self.unreachable_broker():
            self.post()

        self.assertEqual(1, EmailDispatch.objects.pending().count())
        self.assertEqual(0, len(mail.outbox))
        self.assertEqual(User.objects.count(), 1)


class ThrottleTests(EndpointTestCase):
    def test_the_limit_bites(self):
        """Unauthenticated and server-to-server, so this stands in for CSRF.

        The rate is read when the throttle is constructed, at import time, so it
        cannot be overridden here -- the test spends the real allowance.
        """
        from app.core.accounts.throttles import CustomerRegisterThrottle

        allowance = CustomerRegisterThrottle().num_requests

        for index in range(allowance):
            self.post(email=f'shopper{index}@example.com')

        response = self.post(email='one-too-many@example.com')

        self.assertEqual(response.status_code, 429)

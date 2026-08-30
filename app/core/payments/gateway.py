"""The Payfast protocol: its configuration, its signature, and what makes a
notification real.

Everything here is a pure function of its arguments, with one named exception
(:func:`confirm_with_payfast`, which makes an HTTP call). That is deliberate and
it is the same shape as ``documents.storage``: a signature is the one thing in a
payment integration that is both easy to get subtly wrong and impossible to
debug from the outside -- Payfast answers a bad signature with a generic
refusal -- so every rule that produces one is testable without a merchant
account, a network, or a database.

Four things are worth knowing before changing anything in this file.

**The signature is order-sensitive, and the order is not alphabetical.** Payfast
signs the checkout fields in the order its documentation lists them, which is
:data:`CHECKOUT_FIELD_ORDER`. An incoming notification is signed in the order
the fields *arrived*, which is why :func:`notification_signature` takes a
sequence of pairs rather than a mapping -- a dict built from a request body has
already lost the only ordering that would verify.

**Empty values are omitted, not signed as empty.** A field present with a blank
value is left out of the signed string entirely. Signing it as ``key=`` produces
a valid-looking signature that Payfast rejects.

**The encoding has to match PHP's ``urlencode``.** Spaces become ``+``, hex
escapes are upper case, and ``~`` is escaped -- which Python's ``quote_plus``
does not do, because it treats ``~`` as always safe. Hence :func:`_encode`.

**A notification is not trusted because it parses.** Four independent checks
have to pass, and each exists because the others can be defeated: the source
address, the signature, the amount, and a call back to Payfast asking whether it
sent this. :func:`verify_notification` runs the three that need no network;
``services.apply_notification`` adds the fourth. A notification arriving at a
public URL with a member's account on the other end of it is the one place in
this application where an attacker chooses the input and the outcome is an
active membership.
"""
import hashlib
import ipaddress
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from hmac import compare_digest
from urllib.parse import quote_plus, urlencode
from zoneinfo import ZoneInfo

from django.core.exceptions import ImproperlyConfigured

#: Payfast's own published sandbox merchant. These are not secrets -- they are
#: in Payfast's documentation and every sandbox integration in the country uses
#: them -- and they are the default only when ``DEBUG`` is on, so a deployment
#: that forgets to configure a merchant fails to start rather than quietly
#: taking payments into a shared test account.
SANDBOX_MERCHANT_ID = '10000100'
SANDBOX_MERCHANT_KEY = '46f0cd694581a'
SANDBOX_PASSPHRASE = 'jt7NOE43FZPn'

LIVE_HOST = 'https://www.payfast.co.za'
SANDBOX_HOST = 'https://sandbox.payfast.co.za'

#: Hostnames Payfast sends notifications from. Resolved to addresses at
#: verification time rather than pinned as a list of IPs, because Payfast
#: changes them without notice and a stale list fails closed -- every
#: notification rejected, every membership stuck at Pending payment, and nothing
#: in the logs that names the cause.
NOTIFICATION_HOSTS = (
    'www.payfast.co.za',
    'sandbox.payfast.co.za',
    'w1w.payfast.co.za',
    'w2w.payfast.co.za',
)

#: How Payfast bills a subscription, by its wire code. Named here so the
#: environment can be configured in English -- ``annual`` rather than ``6`` --
#: and so the codes appear once.
FREQUENCIES = {
    'monthly': 3,
    'quarterly': 4,
    'biannual': 5,
    'annual': 6,
}

#: Days one cycle covers, used to work out what a payment bought. Deliberately
#: nominal rather than calendar-exact: it decides when an unpaid membership
#: lapses, and erring long by a day or two is the right direction to err in.
#: See ``services.lapse_overdue``.
CYCLE_DAYS = {
    3: 31,
    4: 93,
    5: 184,
    6: 366,
}

#: ``subscription_type=1`` is a Payfast subscription: Payfast holds the mandate
#: and bills on its own schedule. The alternative, ``2``, is tokenised ad-hoc
#: billing where the merchant initiates every charge -- which would make this
#: application responsible for a billing run, a retry policy and a scheduler it
#: has nowhere to run.
SUBSCRIPTION_TYPE = 1

#: The order Payfast signs the checkout in. Not alphabetical, and not the order
#: these fields are interesting in -- it is the order its documentation lists,
#: and it is the whole reason a checkout signature verifies.
CHECKOUT_FIELD_ORDER = (
    'merchant_id',
    'merchant_key',
    'return_url',
    'cancel_url',
    'notify_url',
    'name_first',
    'name_last',
    'email_address',
    'cell_number',
    'm_payment_id',
    'amount',
    'item_name',
    'item_description',
    'custom_int1',
    'custom_int2',
    'custom_int3',
    'custom_int4',
    'custom_int5',
    'custom_str1',
    'custom_str2',
    'custom_str3',
    'custom_str4',
    'custom_str5',
    'email_confirmation',
    'confirmation_address',
    'payment_method',
    'subscription_type',
    'billing_date',
    'recurring_amount',
    'frequency',
    'cycles',
)

#: Payfast quotes and bills in South African time. The project runs on UTC, so a
#: registration completed after 22:00 UTC would compute yesterday's date -- and
#: Payfast refuses a ``billing_date`` in the past.
BILLING_TIMEZONE = ZoneInfo('Africa/Johannesburg')

#: How long the confirmation call to Payfast may take. Short on purpose: it runs
#: inside the notification request, and Payfast retries a notification we fail
#: to answer. Hanging on it would turn one slow call into a stuck worker.
CONFIRM_TIMEOUT_SECONDS = 10


class NotificationRejected(Exception):
    """A notification did not prove it came from Payfast.

    Carries a ``reason`` that is safe to log and deliberately not safe to
    return: telling a caller *which* check it failed tells an attacker which one
    to fix next.
    """

    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class PayfastSettings:
    """Everything needed to build a checkout and to verify a notification.

    Frozen, and built once at startup by :func:`payfast_config`, so the values a
    request works with cannot have been changed by an earlier request. Tests
    build one directly rather than patching the environment.
    """

    merchant_id: str
    merchant_key: str
    passphrase: str
    sandbox: bool
    return_url: str
    cancel_url: str
    notify_url: str
    #: Where a checkout token becomes a page the member can pay from, without
    #: the token. The emailed fallback link is this plus the token, so it is
    #: configured rather than derived from ``return_url`` -- deriving it would
    #: make the address of one page a function of the address of another.
    checkout_url: str
    amount: Decimal
    frequency: int
    cycles: int
    item_name: str
    item_description: str
    #: Whether the notification endpoint is reached through a reverse proxy, in
    #: which case ``REMOTE_ADDR`` is the proxy and the client address has to come
    #: from ``X-Forwarded-For``. Off by default: trusting that header when
    #: nothing overwrites it hands an attacker the source check outright.
    behind_proxy: bool = False
    #: How long a checkout link stays usable. A day: long enough for a member
    #: who abandoned the Payfast page to come back from the emailed link, short
    #: enough that a link found in an inbox a year later is inert.
    checkout_ttl_seconds: int = 86_400

    @property
    def host(self):
        return SANDBOX_HOST if self.sandbox else LIVE_HOST

    @property
    def process_url(self):
        """Where the member's browser POSTs the signed checkout."""
        return self.host + '/eng/process'

    @property
    def validate_url(self):
        """Where we ask Payfast whether it sent a notification."""
        return self.host + '/eng/query/validate'

    @property
    def recurring_amount(self):
        """What each renewal costs.

        Equal to the first payment, deliberately: a joining fee that differs
        from the renewal is a product decision nobody has taken, and inventing
        one here would hide it.
        """
        return self.amount

    @property
    def cycle_days(self):
        """How long one paid cycle covers. See :data:`CYCLE_DAYS`."""
        return CYCLE_DAYS[self.frequency]


def _money(raw, name):
    """A money amount from the environment, or a named refusal."""
    try:
        amount = Decimal(raw)
    except (InvalidOperation, TypeError, ValueError):
        raise ImproperlyConfigured(
            f'{name} is set to "{raw}", which is not an amount. Give it rands '
            'and cents, e.g. 150.00.'
        ) from None
    if amount <= 0:
        raise ImproperlyConfigured(
            f'{name} is set to "{raw}". A membership subscription must cost '
            'something; there is no free tier to configure.'
        )
    return amount.quantize(Decimal('0.01'))


def payfast_config(environ, debug=False):
    """Read the Payfast settings out of an environment mapping.

    A pure function of ``environ``, which is what makes every refusal below
    testable without a merchant account -- the same reason
    ``documents.storage.documents_storage_config`` is written this way.

    **With ``debug`` on and nothing configured, this returns Payfast's published
    sandbox merchant** and localhost URLs, so the whole flow works on a fresh
    clone with no credentials. Notifications still will not arrive, because
    Payfast cannot reach a localhost ``notify_url``; the ``payfast_notify``
    management command stands in for them.

    **With ``debug`` off, everything is required and startup fails without it.**
    A payment integration that silently falls back to a sandbox is one that
    takes a member's money into an account nobody is watching.

    :raises ImproperlyConfigured: named, one variable at a time.
    """

    def value(name, default=''):
        return (environ.get(name) or '').strip() or default

    merchant_id = value('DJANGO_PAYFAST_MERCHANT_ID')
    merchant_key = value('DJANGO_PAYFAST_MERCHANT_KEY')
    passphrase = value('DJANGO_PAYFAST_PASSPHRASE')

    if debug and not merchant_id and not merchant_key:
        merchant_id = SANDBOX_MERCHANT_ID
        merchant_key = SANDBOX_MERCHANT_KEY
        passphrase = passphrase or SANDBOX_PASSPHRASE

    sandbox_raw = value('DJANGO_PAYFAST_SANDBOX')
    # Live is never the default. A deployment that means to take real money says
    # so, rather than arriving there by leaving a variable unset.
    sandbox = (
        sandbox_raw.lower() in {'1', 'true', 'yes', 'on'} if sandbox_raw else True
    )

    if not merchant_id or not merchant_key:
        raise ImproperlyConfigured(
            'DJANGO_PAYFAST_MERCHANT_ID and DJANGO_PAYFAST_MERCHANT_KEY must '
            'both be set. Both are on the Payfast dashboard; the key is a '
            'secret and belongs in application settings, not in source control.'
        )

    # Required rather than optional, and it is not only about the signature:
    # Payfast will not accept a subscription from a merchant with no passphrase
    # set, so an integration without one fails at the checkout instead of here.
    if not passphrase:
        raise ImproperlyConfigured(
            'DJANGO_PAYFAST_PASSPHRASE is not set. Set a passphrase on the '
            'Payfast account (Settings > Security) and put the same value here: '
            'without one the signature protects nothing and Payfast refuses '
            'subscriptions outright.'
        )

    fallbacks = {
        'DJANGO_PAYFAST_RETURN_URL': 'http://localhost:3000/signup/paid',
        'DJANGO_PAYFAST_CANCEL_URL': 'http://localhost:3000/signup/cancelled',
        'DJANGO_PAYFAST_NOTIFY_URL': (
            'http://localhost:8000/api/payments/payfast/notify'
        ),
        'DJANGO_MEMBERSHIP_CHECKOUT_URL': 'http://localhost:3000/pay',
    }
    urls = {}
    for name, fallback in fallbacks.items():
        url = value(name, fallback if debug else '')
        if not url:
            raise ImproperlyConfigured(
                f'{name} is not set. Four addresses are needed: where to send a '
                'member who paid, where to send one who cancelled, where '
                'Payfast notifies this application server-to-server, and the '
                'page a checkout token is paid from.'
            )
        if not debug and not url.startswith('https://'):
            raise ImproperlyConfigured(
                f'{name} is set to "{url}", which is not https. A payment '
                'redirect over plain http is one that anything on the network '
                'path can rewrite.'
            )
        urls[name] = url.rstrip('/')

    amount = _money(
        value('DJANGO_MEMBERSHIP_SUBSCRIPTION_AMOUNT', '150.00' if debug else ''),
        'DJANGO_MEMBERSHIP_SUBSCRIPTION_AMOUNT',
    )

    frequency = value('DJANGO_MEMBERSHIP_SUBSCRIPTION_FREQUENCY', 'monthly').lower()
    if frequency not in FREQUENCIES:
        raise ImproperlyConfigured(
            f'DJANGO_MEMBERSHIP_SUBSCRIPTION_FREQUENCY is set to "{frequency}". '
            f'It must be one of: {", ".join(sorted(FREQUENCIES))}.'
        )

    cycles = value('DJANGO_MEMBERSHIP_SUBSCRIPTION_CYCLES', '0')
    if not cycles.isdigit():
        raise ImproperlyConfigured(
            f'DJANGO_MEMBERSHIP_SUBSCRIPTION_CYCLES is set to "{cycles}". It '
            'must be a whole number of billing cycles, or 0 for "until the '
            'member cancels".'
        )

    return PayfastSettings(
        merchant_id=merchant_id,
        merchant_key=merchant_key,
        passphrase=passphrase,
        sandbox=sandbox,
        return_url=urls['DJANGO_PAYFAST_RETURN_URL'],
        cancel_url=urls['DJANGO_PAYFAST_CANCEL_URL'],
        notify_url=urls['DJANGO_PAYFAST_NOTIFY_URL'],
        checkout_url=urls['DJANGO_MEMBERSHIP_CHECKOUT_URL'],
        amount=amount,
        frequency=FREQUENCIES[frequency],
        cycles=int(cycles),
        item_name=value(
            'DJANGO_MEMBERSHIP_SUBSCRIPTION_ITEM_NAME', 'Club membership'
        ),
        # Reaches the member's bank statement and the Payfast receipt, so it
        # says what it is and nothing about cultivation.
        item_description=value(
            'DJANGO_MEMBERSHIP_SUBSCRIPTION_DESCRIPTION',
            'Cultivators Collective membership subscription',
        ),
        # **One deployment fact, one variable.** Django has to know it is behind
        # a proxy too -- SECURE_PROXY_SSL_HEADER and SECURE_SSL_REDIRECT depend
        # on it -- and two independent switches for the same fact is a footgun
        # whose failure mode is setting one of them. So DJANGO_BEHIND_PROXY
        # answers both, and the Payfast-specific spelling stays as an override
        # for the deployment where the two genuinely differ: an edge that
        # terminates TLS but appends to X-Forwarded-For rather than overwriting
        # it is safe for the first and not for the second.
        behind_proxy=(
            value('DJANGO_PAYFAST_BEHIND_PROXY') or value('DJANGO_BEHIND_PROXY')
        ).lower() in {'1', 'true', 'yes', 'on'},
    )


def notification_source_ip(meta, behind_proxy=False):
    """The address a notification actually came from.

    ``REMOTE_ADDR`` unless the endpoint sits behind a reverse proxy, in which
    case that is the proxy and the client is the first entry of
    ``X-Forwarded-For``.

    **That header is only safe to read when the edge overwrites it.** An origin
    that appends to whatever arrived lets a caller prepend an address of their
    choosing and walk straight through :func:`source_is_payfast`, which is why
    reading it is opt-in per deployment rather than automatic. Azure Front Door
    and Application Gateway both overwrite; a bare container behind nothing does
    not, and must leave ``DJANGO_PAYFAST_BEHIND_PROXY`` unset.

    The port is stripped: App Service writes ``client:port`` rather than a bare
    address.
    """
    if behind_proxy:
        forwarded = (meta.get('HTTP_X_FORWARDED_FOR') or '').split(',')[0].strip()
        if forwarded:
            # IPv6 arrives bracketed as [::1]:443; IPv4 as 1.2.3.4:443.
            if forwarded.startswith('['):
                return forwarded.partition(']')[0].lstrip('[')
            return forwarded.rsplit(':', 1)[0] if forwarded.count(':') == 1 else forwarded
    return (meta.get('REMOTE_ADDR') or '').strip()


def _encode(value):
    """URL-encode one value the way PHP's ``urlencode`` does.

    Payfast computes its side of the signature in PHP, so this has to match it
    exactly: spaces become ``+``, escapes are upper case, and ``~`` is escaped.
    Python's ``quote_plus`` agrees on the first two and not the third -- it
    treats ``~`` as unreserved, which it is, and which is beside the point here.
    """
    return quote_plus(str(value), safe='').replace('~', '%7E')


def signature_over(pairs, passphrase):
    """MD5 of ``key=value&...`` over ``pairs``, with the passphrase appended.

    ``pairs`` is an ordered sequence, because both signatures Payfast computes
    are order-sensitive and the two orders are different -- see the module
    docstring. Empty values are dropped rather than signed as empty.

    MD5 is not a choice. It is what Payfast computes, so it is what verifies;
    the integrity of the exchange rests on the passphrase and on
    :func:`confirm_with_payfast`, not on the digest being a modern one.
    """
    parts = [
        f'{key}={_encode(str(value).strip())}'
        for key, value in pairs
        if str(value).strip() != ''
    ]
    if passphrase:
        parts.append(f'passphrase={_encode(passphrase.strip())}')
    return hashlib.md5('&'.join(parts).encode('utf-8')).hexdigest()


def checkout_signature(fields, passphrase):
    """Sign a checkout, in Payfast's documented field order.

    A key not in :data:`CHECKOUT_FIELD_ORDER` would not be signed and would
    make Payfast refuse the checkout, so passing one is a mistake rather than a
    no-op -- and it is refused here instead of there.
    """
    unknown = set(fields) - set(CHECKOUT_FIELD_ORDER)
    if unknown:
        raise ValueError(
            'Not Payfast checkout fields: ' + ', '.join(sorted(unknown))
        )
    return signature_over(
        [(key, fields[key]) for key in CHECKOUT_FIELD_ORDER if key in fields],
        passphrase,
    )


def notification_signature(pairs, passphrase):
    """Sign an incoming notification, in the order its fields arrived.

    ``signature`` is dropped if present; everything else is signed, including
    fields this application does not read. Payfast adds fields over time, and a
    verifier that signed only the ones it understood would start failing the day
    it did.
    """
    return signature_over(
        [(key, value) for key, value in pairs if key != 'signature'], passphrase
    )


def payfast_addresses(hosts=NOTIFICATION_HOSTS):
    """Every address the Payfast notification hosts currently resolve to.

    Resolution failures are swallowed per host rather than raised: with four
    hosts, one unreachable resolver must not reject every notification. If they
    all fail the set is empty and :func:`source_is_payfast` says no, which is
    the safe direction -- Payfast retries, and the alternative is trusting an
    unverified caller.
    """
    addresses = set()
    for host in hosts:
        try:
            addresses.update(socket.gethostbyname_ex(host)[2])
        except OSError:
            continue
    return addresses


def source_is_payfast(ip, addresses=None):
    """Whether ``ip`` is one of Payfast's notification addresses.

    The weakest of the four checks and the cheapest, which is why it runs first.
    It is here because the signature alone does not bind a notification to
    Payfast: anyone who ever learns the passphrase can sign one, and the
    passphrase travels to Payfast on every checkout.
    """
    if not ip:
        return False
    if addresses is None:
        addresses = payfast_addresses()
    return ip in addresses


def address_is_private(ip):
    """Whether ``ip`` is on a private network, and therefore cannot be Payfast.

    Only ever used to explain a rejection. A notification whose source address
    is private did not come from the internet, which in a deployment means it
    came from the ingress proxy -- so ``DJANGO_PAYFAST_BEHIND_PROXY`` is unset
    and ``notification_source_ip`` is reading ``REMOTE_ADDR``. That is the
    single most likely cause of a rejected notification and the hardest to guess
    from the log line without this, because "source address is not Payfast" is
    equally what an attacker looks like.

    Never a decision: it widens nothing and admits nobody. ``source_is_payfast``
    has already said no by the time this is asked.
    """
    try:
        return ipaddress.ip_address(ip).is_private
    except ValueError:
        # Not an address at all -- an empty REMOTE_ADDR, or a header carrying
        # something that is not one. Nothing useful to say about it.
        return False


def amount_matches(posted_amount, expected):
    """Whether the notification's gross amount is what we asked for.

    Compared to the cent, and against the amount *this application* configured
    rather than against anything in the notification. Skipping it is how a
    membership gets activated by a one-rand payment.
    """
    try:
        gross = Decimal(str(posted_amount)).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError):
        return False
    return gross == Decimal(expected).quantize(Decimal('0.01'))


def _constant_time_equal(left, right):
    return compare_digest(str(left).encode(), str(right).encode())


def verify_notification(pairs, config, *, source_ip, addresses=None):
    """The three checks that need no network. Raises rather than returning.

    Ordered so the cheapest refusal happens first and so nothing expensive runs
    for a caller that is not Payfast. The amount is *not* checked here: a
    cancellation carries none, so it belongs with the branch that reads it.

    The fourth check -- :func:`confirm_with_payfast` -- is left to
    ``services.apply_notification``, because it is the only one that can fail
    for a reason worth retrying.

    :raises NotificationRejected: with a loggable reason.
    :returns: the posted fields as a mapping, once they are trustworthy.
    """
    if not source_is_payfast(source_ip, addresses):
        raise NotificationRejected(f'source address {source_ip!r} is not Payfast')

    posted = dict(pairs)

    if posted.get('merchant_id') != config.merchant_id:
        raise NotificationRejected('merchant_id is not this merchant')

    expected = notification_signature(pairs, config.passphrase)
    if not _constant_time_equal(posted.get('signature', ''), expected):
        raise NotificationRejected('signature does not verify')

    return posted


def confirm_with_payfast(pairs, config, *, opener=None):
    """Ask Payfast whether it sent this notification. The fourth check.

    Everything before this is computed from the request itself, and a request is
    the attacker's to write. This is the only check that asks the other party,
    and it is the reason a leaked passphrase is not on its own enough to
    activate a membership.

    Returns ``True`` only for a body of exactly ``VALID``. A network failure
    returns ``None`` -- distinct from ``False`` on purpose: "Payfast says no" is
    final, "we could not ask" is worth a retry, and the caller answers Payfast
    differently for each.
    """
    body = urlencode(list(pairs)).encode('utf-8')
    request = urllib.request.Request(
        config.validate_url,
        data=body,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        method='POST',
    )
    send = opener or urllib.request.urlopen
    try:
        with send(request, timeout=CONFIRM_TIMEOUT_SECONDS) as response:
            answer = response.read().decode('utf-8', 'replace').strip()
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    return answer.upper() == 'VALID'


def billing_date(today=None):
    """The date Payfast should bill from, in South African time.

    Today, which makes the first payment immediate and the first renewal one
    cycle later. Computed in ``Africa/Johannesburg`` rather than UTC because the
    project runs on UTC and Payfast refuses a date in the past -- a registration
    at 23:00 SAST would otherwise send yesterday.
    """
    from django.utils import timezone

    if today is not None:
        return today
    return timezone.now().astimezone(BILLING_TIMEZONE).date()


def checkout(config, *, m_payment_id, today=None):
    """The signed field set a member's browser POSTs to Payfast.

    Returns ``{'url': ..., 'fields': {...}}``, ready to render as hidden inputs.

    **It carries no personal data at all** -- no name, no email address, no
    mobile number -- and Payfast requires none. That is a decision rather than
    an omission: these fields are fetched over a URL, and a URL is a thing that
    gets shared, logged and cached. What crosses is the merchant's own
    identifiers, the price, and ``m_payment_id``, an opaque reference that
    identifies a subscription and says nothing about who holds it. The member
    types their own details on Payfast's page, which is where the card is typed
    anyway. The cost is a slightly longer checkout; see
    ``design/features/payments.md``.
    """
    if not isinstance(m_payment_id, str) or not m_payment_id.strip():
        raise ValueError('m_payment_id is required and must be a string.')

    fields = {
        'merchant_id': config.merchant_id,
        'merchant_key': config.merchant_key,
        'return_url': config.return_url,
        'cancel_url': config.cancel_url,
        'notify_url': config.notify_url,
        'm_payment_id': m_payment_id,
        'amount': f'{config.amount:.2f}',
        'item_name': config.item_name,
        'item_description': config.item_description,
        'subscription_type': str(SUBSCRIPTION_TYPE),
        'billing_date': billing_date(today).isoformat(),
        'recurring_amount': f'{config.recurring_amount:.2f}',
        'frequency': str(config.frequency),
        'cycles': str(config.cycles),
    }
    fields['signature'] = checkout_signature(fields, config.passphrase)
    return {'url': config.process_url, 'fields': fields}


def sandbox_settings(**overrides):
    """A :class:`PayfastSettings` on Payfast's sandbox.

    For the test suite and the development notification command. No request path
    reaches this -- settings are read once from the environment at startup.
    """
    base = PayfastSettings(
        merchant_id=SANDBOX_MERCHANT_ID,
        merchant_key=SANDBOX_MERCHANT_KEY,
        passphrase=SANDBOX_PASSPHRASE,
        sandbox=True,
        return_url='http://localhost:3000/signup/paid',
        cancel_url='http://localhost:3000/signup/cancelled',
        notify_url='http://localhost:8000/api/payments/payfast/notify',
        checkout_url='http://localhost:3000/pay',
        amount=Decimal('150.00'),
        frequency=FREQUENCIES['monthly'],
        cycles=0,
        item_name='Club membership',
        item_description='Cultivators Collective membership subscription',
    )
    return replace(base, **overrides) if overrides else base

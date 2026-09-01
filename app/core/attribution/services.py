"""Turning what a browser reported into the two rows worth keeping.

Everything that arrives here came out of a cookie, which means it came from the
client, which means none of it is trusted. One rule governs the whole module:

**Attribution never refuses anything.** No function here raises. A registration
must not fail because a marketing parameter was 400 characters long, arrived in
a shape nobody planned for, or claimed to have happened in 2043. Every value is
cleaned, capped, or dropped, and a payload with nothing usable left in it records
nothing at all -- which is the same outcome as a visitor who arrived untagged,
and is therefore an outcome the rest of the platform already handles.

That is why validation here looks unlike ``common.validators``, which exists to
refuse. These are not fields a member typed and can correct; they are labels the
club put in its own links, read back off a URL. The worst case for a bad one is a
row in a report, and the worst case for refusing one is a member who could not
join.

Two touches are written per conversion at most, and one where they are the same
-- see :class:`~app.core.attribution.models.Attributed` on why that saving is
worth having.
"""
import re
from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import (
    ADDRESS_LENGTH,
    CLICK_ID_LENGTH,
    LABEL_LENGTH,
    CampaignTouch,
    ClickNetwork,
)

#: The five parameters, in the order every analytics product prints them.
CAMPAIGN_FIELDS = ('source', 'medium', 'campaign', 'term', 'content')

#: How far past "now" a browser-asserted arrival time may sit before it is
#: dropped. Clock skew on a phone is seconds to minutes; five minutes is
#: generous and still refuses a fabricated date.
SEEN_AT_FUTURE_TOLERANCE = timedelta(minutes=5)

#: How old a browser-asserted arrival time may be before it is dropped.
#:
#: **Not the cookie's own window restated.** That window lives in the frontend
#: and will be tuned; a copy of it here would silently start discarding valid
#: first touches the day somebody widened it. This is the looser question -- past
#: which point is a date a browser reports simply not credible -- and thirteen
#: months answers it while leaving any plausible cookie life well inside.
SEEN_AT_MAX_AGE = timedelta(days=400)

#: Every run of whitespace, including the tabs and newlines a hand-built link
#: occasionally carries.
_WHITESPACE = re.compile(r'\s+')

#: Control characters, which have no business in a label and which a log or a
#: CSV export would render as something else entirely.
_CONTROL = re.compile(r'[\x00-\x1f\x7f]')


def _text(value, limit):
    """``value`` as a single-line string of at most ``limit`` characters.

    Anything that is not a string becomes ``''`` rather than raising: the caller
    is a parsed request body, and a number, a list or a null in one of these
    positions is a caller getting the shape wrong, not a member getting a form
    wrong.

    Cut rather than refused. See the module docstring, and ``LABEL_LENGTH``.
    """
    if not isinstance(value, str):
        return ''

    # Whitespace first, control characters second, and the order is not
    # cosmetic. A tab is both, so stripping control characters first deletes it
    # and turns `cape\ttown` into one word; collapsing first turns it into a
    # space and leaves the remaining unprintables -- a null, a bell -- to go.
    collapsed = _WHITESPACE.sub(' ', value)
    return _CONTROL.sub('', collapsed).strip()[:limit]


def _label(value):
    """One of the five ``utm_*`` values, lower-cased.

    The lower-casing is the whole reason this is separate from ``_text``.
    ``Instagram`` and ``instagram`` are one channel, and every analytics product
    that does not fold them spends its life explaining why one campaign appears
    three times. Folded here, at the write, so a report does not have to remember
    to -- and so the reporting index is over the folded form.
    """
    return _text(value, LABEL_LENGTH).lower()


def _address(value):
    """A referring URL or a landing path, with its query string removed.

    The stripping is defensive rather than the main event: the frontend already
    sends an origin and a path, having taken the query off where it could see
    the whole URL. This is the second cut, for a caller that is not that
    frontend. See ``CampaignTouch.referrer`` on why the query goes.

    Not parsed with ``urlsplit``, and not validated as a URL. A referrer that is
    not a well-formed URL is still evidence of where somebody came from, and a
    ``ValueError`` from a parser would be this module breaking its one rule.
    """
    return _text(value, ADDRESS_LENGTH).split('?')[0].split('#')[0]


def _click(network, click_id):
    """The click network and its id, or two blanks.

    All or nothing, matching the database's own constraint: an id whose network
    is not one this platform knows reconciles against nothing, and a network with
    no id is a fact ``source`` already carries.
    """
    network = _text(network, 16).lower()
    click_id = _text(click_id, CLICK_ID_LENGTH)

    if network not in ClickNetwork.values or not click_id:
        return '', ''

    return network, click_id


def _seen_at(value, now):
    """When the visit happened, or ``None`` where that cannot be believed.

    Parsed here rather than by the schema, and that is the point of it: a
    ``datetime`` field on ``TouchIn`` would turn a malformed timestamp into a 422
    and refuse a registration over a marketing cookie. ``parse_datetime``
    answers ``None`` for a string it does not recognise and raises only for one
    that is well formed and impossible -- the 31st of February -- which is caught.

    Four ways to lose it, and each is a value that would be worse than a blank: a
    shape that is not a time at all, a naive one, an instant in the future, and
    an instant older than a browser could credibly still be holding. The naive
    case is refused rather than assumed: with ``USE_TZ`` on there is no zone to
    guess, and guessing would put every first touch two hours out.

    See ``CampaignTouch.seen_at`` on why this one timestamp comes from the client
    at all.
    """
    if isinstance(value, str):
        try:
            value = parse_datetime(value.strip())
        except ValueError:
            return None

    if value is None or not hasattr(value, 'tzinfo'):
        return None

    if timezone.is_naive(value):
        return None

    if value > now + SEEN_AT_FUTURE_TOLERANCE:
        return None

    if value < now - SEEN_AT_MAX_AGE:
        return None

    return value


def touch_fields(raw, *, storefront, now=None):
    """The column values for one touch, or ``None`` if it says nothing.

    ``None`` for an empty payload is the important half of this function. A row
    naming no campaign, no click and no referring site counts as an attributed
    member in every report while answering no question -- so it is not written,
    the record's pointer stays null, and "we do not know" stays distinguishable
    from "they came from nowhere". The database says the same thing through
    ``campaign_touch_says_something``.

    ``landing_path`` alone is not enough to keep a touch. Every arrival has one,
    so a touch carrying nothing else is an ordinary untagged visit.
    """
    if not isinstance(raw, dict):
        return None

    now = now or timezone.now()

    click_network, click_id = _click(raw.get('click_network'), raw.get('click_id'))

    fields = {
        'storefront': storefront,
        'click_network': click_network,
        'click_id': click_id,
        'referrer': _address(raw.get('referrer')),
        'landing_path': _address(raw.get('landing_path')),
        'seen_at': _seen_at(raw.get('seen_at'), now),
    }
    for name in CAMPAIGN_FIELDS:
        fields[name] = _label(raw.get(name))

    says_something = any(
        fields[name] for name in (*CAMPAIGN_FIELDS, 'click_id', 'referrer')
    )
    return fields if says_something else None


def record_touches(*, storefront, first=None, last=None, now=None):
    """Write the touches for one conversion and hand back the pair to point at.

    ``first`` and ``last`` are the two payloads the frontend read out of its
    campaign cookie, either of which may be missing or empty. What comes back is
    ``(first_touch, last_touch)``, ready to be assigned to any record inheriting
    :class:`~app.core.attribution.models.Attributed`.

    Four outcomes, and each is one a caller has to handle without branching:

    * neither payload says anything -- ``(None, None)``, an untagged visitor;
    * one says something -- that touch is written once and returned as both,
      because a conversion whose only known campaign is its last is a conversion
      whose first known campaign is the same one;
    * both say the same thing -- one row, returned twice. They arrived and joined
      in a single visit, which is most conversions;
    * they differ -- two rows.

    Called inside the caller's transaction, deliberately. A registration that
    rolls back must not leave a campaign touch behind claiming a member who does
    not exist, and there is no ``atomic`` here precisely so that this cannot
    commit independently of the thing it explains.
    """
    now = now or timezone.now()

    first_fields = touch_fields(first, storefront=storefront, now=now)
    last_fields = touch_fields(last, storefront=storefront, now=now)

    if first_fields is None and last_fields is None:
        return None, None

    # One known touch stands for both. The alternative -- a first touch and a
    # null last touch -- would make "how many joined on the campaign that found
    # them" unanswerable without knowing which half happened to be missing.
    if first_fields is None:
        first_fields = last_fields
    if last_fields is None:
        last_fields = first_fields

    if first_fields == last_fields:
        touch = CampaignTouch.objects.create(**first_fields)
        return touch, touch

    return (
        CampaignTouch.objects.create(**first_fields),
        CampaignTouch.objects.create(**last_fields),
    )

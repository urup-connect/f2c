"""The shape a conversion carries its campaign in.

Embedded rather than flattened. A payload of twenty ``first_utm_source`` and
``last_utm_source`` keys says the same thing as two nested objects and reads
worse at every call site, and it would have to be spelled out again in each
endpoint that grows attribution. ``CampaignIn`` is written once here and named by
whichever request needs it -- ``RegisterIn`` today, an order or an enquiry
tomorrow.

**Every field is optional and every field is a string.** Two deliberate choices,
both following the one rule in ``services``: attribution never refuses anything.
A missing key is an untagged visitor and not a malformed request, so nothing is
required. And ``seen_at`` is a string rather than a ``datetime`` because a
``datetime`` would be parsed here, by the schema, where a malformed value is a 422
-- a registration refused over a timestamp on a marketing cookie. It is parsed in
``services`` instead, where a value that cannot be read is simply dropped.

The names are the model's, minus the ``utm_`` prefix, so a reader can line the
request up against the table without a mapping table in between.
"""
from ninja import Schema


class TouchIn(Schema):
    """One arrival, as the browser's campaign cookie recorded it.

    Sent twice per conversion -- once as the first touch, once as the last -- and
    the two are frequently identical, which ``services.record_touches`` collapses
    into a single row.
    """

    source: str | None = None
    medium: str | None = None
    campaign: str | None = None
    term: str | None = None
    content: str | None = None

    #: The ad network that tagged the click, as one of ``ClickNetwork``'s values
    #: -- ``google``, ``meta``, ``microsoft``, ``tiktok``. The frontend does the
    #: mapping from ``gclid``, ``fbclid``, ``msclkid`` and ``ttclid``, because it
    #: is the side that reads the URL; anything else is dropped here.
    click_network: str | None = None
    click_id: str | None = None

    #: Origin and path only. The frontend takes the query string off; ``services``
    #: takes it off again for a caller that did not.
    referrer: str | None = None
    landing_path: str | None = None

    #: When the visit happened, as an ISO 8601 instant in UTC. A string on
    #: purpose -- see the module docstring.
    seen_at: str | None = None


class CampaignIn(Schema):
    """The campaign that found somebody, and the one they converted on.

    Both optional. One of the two missing is normal rather than wrong: the
    frontend sends what its cookie holds, and a visitor who arrived once has one
    touch to send.
    """

    first: TouchIn | None = None
    last: TouchIn | None = None

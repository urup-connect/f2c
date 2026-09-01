"""Where somebody came from, recorded once, at the moment they converted.

This app answers one commercial question -- *which campaign brought this
member?* -- and it answers it with the five ``utm_*`` parameters every ad
platform, mail tool and analytics product already speaks, plus the ad-network
click id and the referring site.

Three decisions shape everything here.

**Nothing is stored until somebody converts.** There is no visitor table and no
row per arrival. A campaign-bearing arrival is written into one first-party
cookie by the frontend's ``proxy``, and that cookie is the only record until a
registration succeeds -- at which point the two touches worth keeping are
written here and linked to the record they explain. A visitor who never
registers leaves nothing behind in the database at all, which is both the POPIA
answer and the reason this app has no housekeeping to do for people who merely
looked.

**Two touches, not a journey.** ``first`` is the campaign that found them and
``last`` is the one they converted on, and that pair answers "what should we
spend on" and "what closed it" without keeping a row per click. A full touch
history was considered and not taken: it is a table that grows per visit, it
describes a person's browsing in detail, and it answers a question nobody here
has asked yet. If it is ever wanted it is an additional table pointing at
``CampaignTouch``, not a change to this one.

**A touch is immutable and carries no identifier of its own.** Every column is a
campaign label the club chose when it built the link, a referring site, or a
path on this site. There is no visitor id, no device fingerprint, no IP address
and no third-party cookie -- so a touch on its own identifies nobody. It becomes
personal information only through the record that points at it, which is exactly
why the pointer lives on that record (see :class:`Attributed`) and why deleting a
member's row takes their attribution with it.

**What is not recorded, deliberately.** A visitor arriving with no campaign
parameters and no external referrer -- typing the address, or following a
bookmark -- produces no touch. Their attribution is absent rather than a row
saying "direct", because absence is the honest answer and a stored value would
invite somebody to add "direct" up as though it were a channel that had been
measured. The query for them is ``first_touch__isnull=True``.
"""
import uuid

from django.db import models

from app.core.storefronts.models import Storefront

__all__ = ['Attributed', 'CampaignTouch', 'ClickNetwork']

#: How long a label may be before it is cut. Generous by the standards of a
#: hand-written ``utm_campaign`` and deliberately so: an ad platform's
#: auto-tagged ``utm_content`` can be long, and a truncated label is a report
#: with one odd row in it while a refused one is a registration that failed over
#: a marketing parameter. Nothing here ever refuses -- see ``services``.
LABEL_LENGTH = 200

#: A click id is a token an ad network mints and looks up, not a label somebody
#: typed, so it gets its own width. Google's is the long one.
CLICK_ID_LENGTH = 255

#: A referring origin plus its path, and a landing path on this site. Both are
#: stored without their query strings -- see the fields.
ADDRESS_LENGTH = 255


class ClickNetwork(models.TextChoices):
    """The ad network whose click id this touch carries.

    Stored as the network rather than as the parameter name, so a report reads
    ``google`` instead of ``gclid`` and a second Google parameter -- there are
    already two more of them -- does not arrive as a second channel.

    The id itself is kept because it is the only thing that reconciles a
    registration against money spent: a campaign label says which advert, and
    the click id says which click, which is what the network's own reporting
    joins on.
    """

    GOOGLE = 'google', 'Google Ads'
    META = 'meta', 'Meta (Facebook, Instagram)'
    MICROSOFT = 'microsoft', 'Microsoft Advertising'
    TIKTOK = 'tiktok', 'TikTok'


class CampaignTouchQuerySet(models.QuerySet):
    def recorded_before(self, cutoff):
        """Touches written before ``cutoff``.

        Keyed on ``recorded_at`` rather than on ``seen_at``, and the purge
        depends on it: ``seen_at`` is asserted by a browser and may be null, so
        a retention window measured on it would leave every touch that arrived
        without a usable timestamp behind for ever.
        """
        return self.filter(recorded_at__lt=cutoff)


class CampaignTouch(models.Model):
    """One campaign-bearing arrival, as it was when it happened.

    Written by ``services.record_touches`` and never updated. Two rows per
    conversion at most, and one where the visitor arrived and registered in the
    same visit.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)

    # Which shopfront the arrival was at. The club and the market run separate
    # campaigns and will want separate reports, and without this a source of
    # `instagram` is two channels flattened into one row.
    storefront = models.CharField(
        max_length=16,
        choices=Storefront.choices,
        db_index=True,
        help_text='The shopfront the visitor arrived at.',
    )

    # ------------------------------------------------------------------
    # The five standard parameters
    # ------------------------------------------------------------------
    # Named exactly as the query parameters are, minus the prefix, because these
    # columns exist to be recognised -- by whoever reads the admin, by whoever
    # exports the table, and by the next person to wire a storefront into this.
    #
    # Every one is optional. A link tagged with a source and nothing else is a
    # link the club actually builds, and refusing it would only lose the one
    # dimension it did carry.
    #
    # All five are lower-cased and space-collapsed on the way in -- see
    # `services`. `Instagram`, `instagram` and ` instagram ` are one channel, and
    # a report showing them as three is a report nobody trusts twice.
    source = models.CharField(
        max_length=LABEL_LENGTH,
        blank=True,
        help_text='utm_source — where the click came from, e.g. instagram.',
    )
    medium = models.CharField(
        max_length=LABEL_LENGTH,
        blank=True,
        help_text='utm_medium — how it arrived, e.g. cpc, email, social.',
    )
    campaign = models.CharField(
        max_length=LABEL_LENGTH,
        blank=True,
        help_text='utm_campaign — which campaign, e.g. spring-open-day.',
    )
    term = models.CharField(
        max_length=LABEL_LENGTH,
        blank=True,
        help_text='utm_term — the paid keyword, where there is one.',
    )
    content = models.CharField(
        max_length=LABEL_LENGTH,
        blank=True,
        help_text='utm_content — which creative or link within the campaign.',
    )

    # ------------------------------------------------------------------
    # The ad click
    # ------------------------------------------------------------------
    # The pair is all-or-nothing, and a check constraint holds it that way: an id
    # with no network reconciles against nothing, and a network with no id is a
    # fact `source` already carries.
    click_network = models.CharField(
        max_length=16,
        choices=ClickNetwork.choices,
        blank=True,
        db_index=True,
        help_text='The ad network that tagged the click, where one did.',
    )
    click_id = models.CharField(
        max_length=CLICK_ID_LENGTH,
        blank=True,
        help_text=(
            'The network’s own id for the click — gclid, fbclid, msclkid or '
            'ttclid. What reconciles a signup against ad spend.'
        ),
    )

    # ------------------------------------------------------------------
    # The arrival itself
    # ------------------------------------------------------------------
    # **Query strings are stripped from both, on purpose.** A referring URL's
    # query can carry anything the referring site put in it -- a search term, a
    # session id, somebody's address in a badly built newsletter link -- and none
    # of it is needed to know which site sent the visitor. What is kept is the
    # origin and the path, which is the answer to the question and the whole of
    # it. The landing path is stored without its query for the same reason and
    # one more: the parameters worth keeping are already the columns above.
    referrer = models.CharField(
        max_length=ADDRESS_LENGTH,
        blank=True,
        help_text=(
            'The site that linked here, as origin and path only — no query '
            'string. Blank for a direct arrival.'
        ),
    )
    landing_path = models.CharField(
        max_length=ADDRESS_LENGTH,
        blank=True,
        help_text='The path on this site the visitor arrived on.',
    )

    # Asserted by the browser, and therefore checked rather than believed.
    #
    # Every other timestamp on this platform is stamped by the database, for the
    # reason `DocumentConsent.accepted_at` gives: two clocks for one fact
    # eventually disagree. A **first** touch is the exception that has no choice.
    # It happened before there was any record to stamp -- possibly weeks before
    # -- so the only available answer is the one the cookie carries, and
    # `services` drops a value that is malformed, in the future, or older than
    # the cookie could be, leaving this null instead. A null here means "we know
    # the campaign and not the moment", which is a smaller loss than a date
    # somebody could have typed.
    seen_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            'When the visit happened, as the browser reported it. Empty where '
            'that could not be trusted.'
        ),
    )

    # When this row was written, which is the conversion, and the column every
    # retention decision is made on.
    recorded_at = models.DateTimeField(auto_now_add=True)

    objects = CampaignTouchQuerySet.as_manager()

    class Meta:
        ordering = ('-recorded_at',)
        verbose_name = 'campaign touch'
        verbose_name_plural = 'campaign touches'
        indexes = [
            # The reporting index: "how many members came from this campaign",
            # which is every question this table gets asked.
            models.Index(
                fields=['source', 'medium', 'campaign'],
                name='campaign_touch_by_campaign',
            ),
            models.Index(fields=['-recorded_at'], name='campaign_touch_by_recorded'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(storefront__in=Storefront.values),
                name='campaign_touch_storefront_is_known',
                violation_error_message=(
                    'That is not a storefront this platform serves.'
                ),
            ),
            models.CheckConstraint(
                condition=models.Q(click_network__in=[*ClickNetwork.values, '']),
                name='campaign_touch_click_network_is_known',
                violation_error_message=(
                    'That is not an ad network this platform recognises.'
                ),
            ),
            # The pair, held together by the database rather than only by the
            # service that writes it. Either both are set or neither is.
            models.CheckConstraint(
                condition=(
                    models.Q(click_network='', click_id='')
                    | (~models.Q(click_network='') & ~models.Q(click_id=''))
                ),
                name='campaign_touch_click_is_a_pair',
                violation_error_message=(
                    'A click id needs the network that issued it, and a '
                    'network needs the id.'
                ),
            ),
            # A row that says nothing is worse than no row: it counts as an
            # attributed member in every report while naming no campaign. The
            # service drops an empty touch, and this makes sure nothing else can
            # write one -- a fixture, a data migration, or the admin.
            #
            # `landing_path` is not in this list. Every arrival has one, so
            # including it would make the constraint unfailable and say nothing.
            models.CheckConstraint(
                condition=(
                    ~models.Q(source='')
                    | ~models.Q(medium='')
                    | ~models.Q(campaign='')
                    | ~models.Q(term='')
                    | ~models.Q(content='')
                    | ~models.Q(click_id='')
                    | ~models.Q(referrer='')
                ),
                name='campaign_touch_says_something',
                violation_error_message=(
                    'A campaign touch has to name a source, a campaign, a '
                    'click or a referring site.'
                ),
            ),
        ]

    def __str__(self):
        return self.label

    @property
    def label(self):
        """How this touch reads in a list: ``source / medium / campaign``.

        The three dimensions a report is built on, in the order every analytics
        product prints them, with a dash where one is missing so the shape of the
        line stays the same. Falls back to the referring site and then to the
        click network, because a touch always says *something* -- the check
        constraint above sees to that -- and a blank cell in an admin list is
        indistinguishable from a bug.
        """
        named = ' / '.join(
            value or '—' for value in (self.source, self.medium, self.campaign)
        )
        if named != '— / — / —':
            return named
        return self.referrer or self.get_click_network_display() or '—'


class Attributed(models.Model):
    """Two pointers, for any record that wants to know what brought it.

    Inherited rather than repeated: the alternative is the ten campaign columns
    twice over on every model that cares, which is twenty columns per table, a
    migration per table when a parameter is added, and a report that has to know
    which table it is reading. This way a record that wants attribution gains two
    foreign keys and every campaign question is asked of one table.

    ``ClubMembership`` is the first and, for now, the only user. A market
    customer, an order, or an enquiry form gains the same two columns by
    inheriting this and nothing else changes.

    **A generic foreign key was not used**, and this platform has none anywhere.
    Pointing from the touch at "some row in some table" costs a join through
    ``django_contenttypes`` on every read, cannot be constrained by the database,
    and would let a touch point at a row that has been deleted. Pointing from the
    record at the touch is one column, one index and a real foreign key.

    ``first`` and ``last`` are the same row where somebody arrived and registered
    in one visit. That is a saving worth having -- most conversions are one visit
    -- and it means "how many members arrived and joined the same day" is
    ``first_touch_id=F('last_touch_id')`` rather than a comparison of ten columns.
    """

    # SET_NULL, not PROTECT or CASCADE.
    #
    # The retention purge deletes touches on a schedule, and each of the other
    # two answers is wrong in its own way: PROTECT would make the purge fail
    # against every attributed member, and CASCADE would delete the member along
    # with the marketing label that explains them. Losing the attribution and
    # keeping the record is the only sane direction, and a null here already
    # means "not known", which is exactly what it becomes.
    #
    # `related_name='+'`: no reverse accessor. A touch belongs to one record and
    # is always read from it, so a reverse manager per inheriting model would be
    # names nobody calls -- and the useful direction, "which members came from
    # this campaign", is a filter on the record's own manager.
    first_touch = models.ForeignKey(
        'attribution.CampaignTouch',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        help_text='The campaign that first brought this visitor here.',
    )
    last_touch = models.ForeignKey(
        'attribution.CampaignTouch',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        help_text=(
            'The campaign on the visit they converted on. The same row as the '
            'first touch where that was one and the same visit.'
        ),
    )

    class Meta:
        abstract = True

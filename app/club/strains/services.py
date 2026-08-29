"""What an administrator may do to the strain catalogue, and the rules doing it.

The endpoints in ``strains.api`` are translations of the exceptions raised here
into status codes and nothing more, which is the shape ``accounts.profile`` and
``membership.api`` already have. Every rule is in this module, and so is the
permission check -- ``platform.manage_strain_catalogue``, asked of the caller
before anything is read or written, so that a router is not the only thing
between a member and the catalogue.

**Five rules live here that nothing in SQL can state**, and each is here rather
than on the model for a reason worth reading:

1. **Name uniqueness reports against ``name``.** The unique index is on ``slug``,
   which is ``editable=False`` -- and Django's ``full_clean`` excludes
   non-editable fields from validation, then skips any constraint that mentions
   one. So ``Strain.full_clean()`` does *not* check the slug's uniqueness, and
   without the check below a second "OG Kush" would reach the database and come
   back as an ``IntegrityError``: a 500, rather than a sentence beside the name
   field. This is the only place that refusal exists for an API caller.
2. **``exclusive_to`` must hold the cultivator role.** The column is a foreign
   key to ``AUTH_USER_MODEL``, so the database will accept any account --
   a member, a sharing member, an administrator. The Django admin narrows the
   picker in ``admin.cultivator_choices`` and that narrowing is a property of a
   *widget*, so an API caller had nothing enforcing it. Now both go through the
   same rule.
3. **An unavailable aroma or effect may be added to nothing new.** The field's
   own help text is the specification -- "Clear this to stop offering the term on
   new strains. Existing strains keep it." -- which is a rule about a *change*
   rather than about a state, so no constraint can hold it. A strain already
   carrying a retired term keeps it through every subsequent save.
4. **The three JSON columns are bounded.** They are free-form by design and a
   JSON column has no length. An administrator is trusted, but "trusted" is not
   "the request body is whatever arrived", and an unbounded column is a row that
   can be made too large to serialise back out.
5. **Retirement, never deletion.** There is no delete in this module. A strain
   with listings behind it, and listings with plants behind them, is a record the
   club has sold against; ``on_delete=PROTECT`` on both keys says so, and the
   answer to a strain the club no longer wants is ``StrainStatus.INACTIVE``,
   which ``StrainQuerySet.browsable`` then excludes platform-wide. ``retire``
   reports how many live offers that took off the shelf, because that is the
   consequence an administrator cannot see from the strain's own row.

The vocabularies work the same way and for the same reason: ``is_available`` is
cleared, the row stays, and every strain already carrying the term keeps it.
Deleting an ``Aroma`` would silently remove it from every strain that used it,
with nothing to say it had happened.
"""
from django.contrib.auth import get_user_model

from app.commerce.producers.models import Producer
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.utils.text import slugify


from .models import (
    Aroma,
    CultivatorStrainListing,
    Effect,
    ListingStatus,
    Strain,
    StrainStatus,
)

#: The single action this module answers to. ``roles.ADMIN_ACTIONS`` describes
#: it as "Create, read, update and delete strain listings platform-wide" -- the
#: delete half of which is served by retirement, for the reason the module
#: docstring gives.
MANAGE_CATALOGUE = 'platform.manage_strain_catalogue'

#: The vocabularies, by the segment that names one in a URL. A mapping rather
#: than two copies of every endpoint: the two models are identical apart from
#: their table, and ``SlugFromName`` is where that identity is already recorded.
TERM_MODELS = {'aromas': Aroma, 'effects': Effect}

#: Every column an administrator may write. The API schema is the outer
#: allow-list and this is the inner one, deliberately duplicated: a field added
#: to the schema by accident cannot reach ``setattr`` without also being added
#: here, and the fields absent from both are absent on purpose -- ``slug`` is
#: derived, ``id`` and the timestamps are the record's own.
WRITABLE_FIELDS = frozenset({
    'status',
    'exclusive_to',
    'name',
    'strain_type',
    'genetic_lineage',
    'breeder_origin',
    'description',
    'thc_content',
    'cbd_content',
    'other_cannabinoids',
    'terpene_profile',
    'disease_resistance',
    'flowering_time_weeks',
    'preferred_growing_environment',
    'difficulty_level',
})

#: The free-form columns, bounded by ``_validated_mapping`` below.
JSON_FIELDS = ('other_cannabinoids', 'terpene_profile', 'disease_resistance')

#: How much a JSON column may hold. Generous enough for every terpene anybody
#: quotes and small enough that the row stays a row.
MAX_JSON_KEYS = 40
MAX_JSON_KEY_LENGTH = 40
MAX_JSON_VALUE_LENGTH = 100


def _authorise(user):
    """Refuse a caller who does not hold the catalogue permission.

    ``PermissionDenied`` rather than ``ValidationError``, matching
    ``accounts.profile.update_profile``: nothing about the submission is wrong,
    the caller simply may not do this. Asked on reads as well as writes -- the
    catalogue is not secret, but this module is the administrator's view of it,
    carrying listing counts and reserved-to names that the member-facing browse
    in Block 5 has no business exposing.
    """
    if user is None or not user.has_perm(MANAGE_CATALOGUE):
        raise PermissionDenied('This account may not manage the strain catalogue.')


# ----------------------------------------------------------------------
# Reads
# ----------------------------------------------------------------------

def _listings_queryset():
    """Every offer against a strain, with what an administrator needs to see.

    ``plant_count`` is the number that decides whether a listing can ever go
    away: ``Plant.listing`` is ``PROTECT``, so a listing with plants behind it
    is permanent, and an administrator looking at a strain they mean to retire
    should be told that before they act rather than after.
    """
    return (
        CultivatorStrainListing.objects
        .select_related('cultivator')
        .annotate(plant_count=models.Count('plants', distinct=True))
        .prefetch_related('finished_product_types')
        .order_by('cultivator__trading_name')
    )


def catalogue(user, *, status=None, strain_type=None, search=None):
    """The whole catalogue as the administrator's list screen reads it.

    The two annotations are the reason this is not ``Strain.objects.all()``.
    Both counts are on every row because the list is where a strain is chosen
    for retirement, and "how many growers are selling this" is the one thing
    that decision turns on -- computed in the query rather than per row, which
    is what stops a catalogue of two hundred strains being four hundred queries.

    ``distinct=True`` on both, because two aggregates over the same relation in
    one query multiply each other's rows otherwise.

    Every filter is optional and absent means unfiltered. ``search`` covers the
    three text columns an administrator would recognise a strain by; the JSON
    columns are deliberately not searched -- MySQL cannot index one without a
    generated column beside it, and a filter that table-scans on a screen
    somebody types into is a filter that gets slower with the catalogue.
    """
    _authorise(user)

    strains = (
        Strain.objects
        .select_related('exclusive_to')
        .annotate(
            listing_total=models.Count('listings', distinct=True),
            listing_live=models.Count(
                'listings',
                filter=models.Q(listings__status=ListingStatus.LISTED),
                distinct=True,
            ),
        )
        # Stated, not inherited. `Strain.Meta.ordering` is `('name',)`, and
        # Django stops applying a model's default ordering once the query
        # carries an aggregate -- so without this the list arrives in whatever
        # order the rows were inserted, which on a screen an administrator scans
        # for a name is no order at all. It looks redundant beside the model's
        # Meta and is not.
        .order_by('name')
    )

    if status:
        strains = strains.filter(status=status)
    if strain_type:
        strains = strains.filter(strain_type=strain_type)
    if search and (term := search.strip()):
        strains = strains.filter(
            models.Q(name__icontains=term)
            | models.Q(genetic_lineage__icontains=term)
            | models.Q(breeder_origin__icontains=term)
        )

    return strains


def strain_detail(user, strain_id):
    """One strain, with its vocabularies and every offer against it.

    Raises ``Strain.DoesNotExist``, which the endpoint turns into a 404. The
    listings come down with the strain rather than from an endpoint of their
    own: they are read-only here -- a grower's commercial terms are not an
    administrator's to edit in passing while curating botanical facts, which is
    the same line ``admin.CultivatorStrainListingInline`` draws -- and the edit
    screen shows them every time, so a second round trip would buy nothing.
    """
    _authorise(user)

    return (
        Strain.objects
        .select_related('exclusive_to')
        .prefetch_related(
            'aromas',
            'effects',
            models.Prefetch('listings', queryset=_listings_queryset()),
        )
        .get(pk=strain_id)
    )


def reservable_cultivators(user):
    """The accounts a strain may be reserved to, for the form's picker.

    The read half of ``_validated_exclusive_to``, and the two have to agree: a
    picker offering an account the write would refuse is a form that refuses
    itself. Same filter, stated once each because one is a queryset and the other
    is a single-object check.

    ``admin.cultivator_choices`` is the third copy of this, and it stays -- the
    Django admin narrows a widget from the model layer and cannot reach a service
    without importing one into an admin module. Named here so the drift is
    findable rather than surprising.

    **What this exposes.** Only an id and a ``display_name``, and that is not a
    detail: section 6.6 of ``roles-and-permissions.md`` makes ``display_name``
    the only name any payload carries, and a picker over the club's growers is
    exactly the sort of endpoint that would otherwise leak an email address to
    make an autocomplete nicer.

    Ordered by trading name, which is what ``Producer.pseudonym`` returns --
    so the list reads alphabetically as drawn.
    """
    _authorise(user)

    # Producers, not people. Reserving a strain and owning a listing are the
    # organisation's, and a picker offering three appointed staff of one farm as
    # three separate cultivators was the shape this had while `cultivator`
    # pointed at a user.
    return Producer.objects.order_by('trading_name')


def vocabularies(user):
    """Both term lists, each with how many strains carry the term.

    One call rather than two, because both pickers are on one form and neither
    screen has a use for one without the other. ``strain_count`` is what tells
    an administrator whether a term is safe to rename or worth retiring -- the
    same column ``admin.AromaEffectAdmin`` puts on its list, for the same
    reason.
    """
    _authorise(user)

    return {
        kind: model.objects.annotate(
            strain_count=models.Count('strains', distinct=True)
        )
        for kind, model in TERM_MODELS.items()
    }


# ----------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------

def _validated_mapping(value):
    """One JSON column, bounded. Returns it, or raises for that field.

    A ``dict`` is guaranteed by the schema, so what is checked here is size:
    how many keys, and how long a key and a value may be. Values are coerced to
    nothing -- a number stays a number and a string stays a string, because
    ``{"CBG": 0.8}`` and ``{"botrytis": "good"}`` are both things these columns
    are for, and the model's help text quotes the first.
    """
    if len(value) > MAX_JSON_KEYS:
        raise ValidationError(
            f'This holds at most {MAX_JSON_KEYS} entries.',
            code='too_many_entries',
        )

    for key, entry in value.items():
        if not str(key).strip():
            raise ValidationError('Every entry needs a name.', code='blank_key')
        if len(str(key)) > MAX_JSON_KEY_LENGTH:
            raise ValidationError(
                f'"{str(key)[:20]}…" is too long for a name -- '
                f'{MAX_JSON_KEY_LENGTH} characters at most.',
                code='key_too_long',
            )
        if len(str(entry)) > MAX_JSON_VALUE_LENGTH:
            raise ValidationError(
                f'The value against "{key}" is too long -- '
                f'{MAX_JSON_VALUE_LENGTH} characters at most.',
                code='value_too_long',
            )

    return value


def _validated_exclusive_to(account_id):
    """The account a strain may be reserved to, or a refusal.

    Takes an **id**, not an instance, and resolves it here. That is deliberate:
    the caller is a request body, so the alternative is an endpoint that fetches
    the account and a service that trusts what it was handed -- and then an
    unknown id is either a 500 from the endpoint or a rule the service does not
    own. Resolving it here means one rule, one refusal, and no caller that can
    smuggle an account past the role check by passing an object.

    ``None`` is the normal case and passes straight through: a strain nobody has
    reserved is a strain any cultivator may offer.

    The role rule is the one ``admin.cultivator_choices`` applies to its picker,
    and moving it here is the point. A narrowed widget is not a rule -- it
    governs one screen, and this API is a second screen. Erased accounts are
    refused along with the wrong role, because ``soft_delete`` leaves the role in
    place deliberately, so the role alone would still admit somebody who has
    left.

    An unknown id gets the same sentence as the wrong role, on purpose. A picker
    cannot produce one, so distinguishing them would only tell a caller
    experimenting with account ids which of them exist.
    """
    if account_id is None:
        return None

    producer = (
        Producer.objects
        .filter(pk=getattr(account_id, 'pk', account_id))
        .first()
    )

    # **A rule was lost here and is not silently gone.** This used to refuse a
    # cultivator who had left, by checking `deleted_at` on their account --
    # "a departing grower must not take a catalogue entry with them", per
    # `Strain.exclusive_to`. A `Producer` is an organisation: it is not erased
    # under POPIA and has no departure state at all, so there is nothing left to
    # check.
    #
    # `is_published` is **not** the substitute. It means "members can see this
    # producer", which is also false for a farm being set up, and reserving a
    # strain to one before it opens is a legitimate thing to do.
    #
    # What is needed is a producer lifecycle -- retired, or left the club -- and
    # that belongs with Block 2 rather than being invented here. Carried in
    # `todo.md`.
    if producer is None:
        raise ValidationError(
            'A strain can only be reserved to a producer on the platform.',
            code='not_a_cultivator',
        )

    return producer


def _validated_name(name, *, exclude_pk=None):
    """A strain name no other strain already wears, or a refusal.

    Checked on the derived slug and reported against ``name``, which is the
    whole reason this function exists -- see point 1 of the module docstring.
    ``slugify`` folds case and spacing, so "OG Kush" and "og  kush" collide
    here exactly as they would in the index, on SQLite and on MySQL alike.

    The window between this and the write is closed by the unique constraint
    rather than by this check: two administrators typing one name in the same
    instant is a race the database wins, and the second write fails loudly. What
    this buys is that the ordinary case -- somebody typing a name that is
    already there -- reads as a sentence beside the field.
    """
    trimmed = (name or '').strip()
    if not trimmed:
        raise ValidationError('A strain needs a name.', code='blank')

    slug = slugify(trimmed)[:100]
    if not slug:
        raise ValidationError(
            'That name has no letters or numbers in it, so the catalogue has '
            'nothing to key it on.',
            code='unsluggable',
        )

    taken = Strain.objects.filter(slug=slug)
    if exclude_pk is not None:
        taken = taken.exclude(pk=exclude_pk)
    if taken.exists():
        raise ValidationError(
            'A strain with that name already exists.', code='duplicate'
        )

    return trimmed


def _validated_terms(model, submitted_ids, *, already_held=()):
    """The terms to attach, or a refusal naming the ones that are retired.

    ``already_held`` is what the strain carries now, and it is what makes point
    3 of the module docstring true: a retired term is refused only when it is
    being *added*. A strain that has carried "gassy" since before the term was
    withdrawn keeps it through every subsequent save, which is what the field's
    help text promises.

    An unknown id is refused rather than ignored. A picker cannot produce one,
    so an id that is not in the table means the request was not built by the
    screen -- and silently dropping it would save a strain with fewer terms than
    the caller asked for and report success.
    """
    wanted = list(dict.fromkeys(submitted_ids))
    if not wanted:
        return []

    found = {term.pk: term for term in model.objects.filter(pk__in=wanted)}

    if missing := [str(pk) for pk in wanted if pk not in found]:
        raise ValidationError(
            'These are not terms in the club’s list: %(terms)s.',
            code='unknown_term',
            params={'terms': ', '.join(missing)},
        )

    held = set(already_held)
    withdrawn = sorted(
        term.name
        for pk, term in found.items()
        if not term.is_available and pk not in held
    )
    if withdrawn:
        raise ValidationError(
            'These terms are no longer offered on new strains: %(terms)s.',
            code='term_withdrawn',
            params={'terms': ', '.join(withdrawn)},
        )

    return [found[pk] for pk in wanted]


def _merged(errors, error):
    """Fold a ``ValidationError`` from ``full_clean`` into a field-keyed dict.

    ``full_clean`` raises one exception carrying every field it refused, and the
    checks above raise one exception each. Both have to reach the caller
    together: an administrator who mistyped a name *and* a THC figure should be
    told both, not told the first and then the second on the next attempt.

    A field this module has already refused is left alone. Its message is the
    specific one -- "a strain with that name already exists" -- and
    ``full_clean``'s would be the generic one underneath it.
    """
    for field, messages in getattr(error, 'message_dict', {}).items():
        errors.setdefault(field, messages)
    return errors


def _apply(strain, fields, *, aromas, effects, creating):
    """Validate a whole submission against ``strain``, then write it.

    The order is the load-bearing part. Everything is validated before anything
    is saved, and the many-to-many is written last, inside the same transaction
    -- so a submission refused for a retired aroma leaves the strain's name,
    price and profile exactly as they were rather than half changed.
    """
    if unknown := set(fields) - WRITABLE_FIELDS:
        # Not a refusal: the caller is this project's own API, and a field
        # reaching here that is not writable is a schema that has drifted from
        # the allow-list. Loud, and never in a response body.
        raise ValueError(f'Not writable on a strain: {", ".join(sorted(unknown))}.')

    errors = {}
    values = dict(fields)

    def resolve(field, resolver):
        """Replace ``values[field]`` with its checked form, or drop it.

        Dropping it on refusal is the part that matters. ``exclusive_to`` arrives
        as an id and is *replaced* by the account it names, so a refused value
        left in place would reach the ``setattr`` loop below as a ``UUID`` being
        assigned to a foreign key -- a ``ValueError`` from Django's descriptor,
        raised before the collected refusals are ever returned. The submission is
        already invalid at that point, so the value has nothing left to do.
        """
        if field not in values:
            return
        try:
            values[field] = resolver(values[field])
        except ValidationError as error:
            errors[field] = error.messages
            del values[field]

    resolve(
        'name',
        lambda name: _validated_name(
            name, exclude_pk=None if creating else strain.pk
        ),
    )
    resolve('exclusive_to', _validated_exclusive_to)
    for json_field in JSON_FIELDS:
        resolve(json_field, _validated_mapping)

    # The terms a strain already carries, read before anything is written.
    # Empty on a create, which is why `creating` is passed rather than derived
    # from `_state.adding`: reading a many-to-many off an unsaved row is a query
    # against a primary key that has a default and no table entry.
    held_aromas = () if creating else {term.pk for term in strain.aromas.all()}
    held_effects = () if creating else {term.pk for term in strain.effects.all()}

    # Two separate lists, not one chained assignment: they are replaced below
    # and only ever read when no error was collected, but a shared empty list
    # behind two names is a trap for whoever edits this next.
    resolved_aromas = []
    resolved_effects = []
    try:
        resolved_aromas = _validated_terms(Aroma, aromas, already_held=held_aromas)
    except ValidationError as error:
        errors['aromas'] = error.messages
    try:
        resolved_effects = _validated_terms(Effect, effects, already_held=held_effects)
    except ValidationError as error:
        errors['effects'] = error.messages

    for field, value in values.items():
        setattr(strain, field, value)

    try:
        # `exclude` names the two fields validated above with better words than
        # `full_clean` has for them. Everything else -- the percentage
        # validators, the choice lists, the flowering-time range, the check
        # constraints -- is the model's own and is checked here rather than
        # restated.
        strain.full_clean(exclude=('name', 'exclusive_to'))
    except ValidationError as error:
        _merged(errors, error)

    if errors:
        raise ValidationError(errors)

    strain.save()
    # `set` rather than `add`: this is a replace, and a term removed on the
    # screen has to come off the row.
    strain.aromas.set(resolved_aromas)
    strain.effects.set(resolved_effects)

    return strain


# ----------------------------------------------------------------------
# Writes
# ----------------------------------------------------------------------

@transaction.atomic
def create_strain(user, *, aromas=(), effects=(), **fields):
    """Add a strain to the catalogue, and return it.

    ``StrainStatus.PENDING`` is the model's default and is left as one: an
    administrator typing in a strain a cultivator asked for has not checked the
    botanical facts yet, and ``member-roles.md`` puts the checking before the
    publishing. Nothing here forces the status -- a caller that sends ``active``
    gets ``active`` -- because the screen has the field on it and an
    administrator entering a strain they know is entitled to publish it in one
    step.
    """
    _authorise(user)

    return _apply(
        Strain(), fields, aromas=aromas, effects=effects, creating=True
    )


@transaction.atomic
def update_strain(user, strain, *, aromas=(), effects=(), **fields):
    """Replace every editable field on ``strain``, and return it.

    A replace rather than a patch, matching ``accounts.profile.update_profile``
    and for the same reason: the screen holds every field and sends every field,
    so behaviour does not depend on what a browser chose to omit. The failure
    mode a patch has here is a JSON column quietly surviving an edit that
    cleared it.
    """
    _authorise(user)

    return _apply(
        strain, fields, aromas=aromas, effects=effects, creating=False
    )


@transaction.atomic
def retire_strain(user, strain):
    """Take a strain out of the catalogue without deleting it.

    Returns ``(strain, listings_taken_down)``. The count is the consequence the
    strain's own row does not show: ``CultivatorStrainListingQuerySet.visible``
    filters on the strain's status as well as the listing's, so retiring one
    strain takes every live offer against it off the shelf at once -- without
    an administrator having had to visit each grower's listings, and without
    any of those rows changing.

    That is also why the listings are left alone. A withdrawn listing is a
    cultivator's own decision to stop offering something; this is the club
    retiring the strain underneath them, and overwriting each listing's status
    would erase the difference and leave nothing to reinstate when the strain
    comes back.

    Idempotent. Retiring a strain that is already inactive is a no-op that
    answers 200 with a count of zero, because a caller that got what it asked
    for should not be told it failed.
    """
    _authorise(user)

    # Counted before the write. Afterwards `visible()` excludes them all, so
    # the same query would answer zero and the administrator would be told
    # nothing came down.
    taken_down = strain.listings.filter(status=ListingStatus.LISTED).count()

    if strain.status == StrainStatus.INACTIVE:
        return strain, 0

    strain.status = StrainStatus.INACTIVE
    # A full save rather than `update_fields`. `updated_at` is `auto_now`, and
    # Django skips an `auto_now` column that a partial save does not name --
    # the same reason `accounts.profile.update_profile` saves in full. A
    # retirement that did not move `updated_at` would be invisible on the list
    # screen, which sorts and reports on it.
    strain.save()

    return strain, taken_down


@transaction.atomic
def create_term(user, kind, *, name, is_available=True):
    """Add one aroma or effect to the club's vocabulary, and return it.

    ``member-roles.md`` has cultivators *requesting* additions to these lists,
    which makes them runtime data an administrator extends -- the reason they
    are lookup tables rather than choice lists in the first place. The request
    itself is a support ticket in Block 11; this is the administrator acting on
    one.
    """
    _authorise(user)

    model = _term_model(kind)
    term = model(is_available=is_available)
    _apply_term(model, term, name=name, creating=True)
    return term


@transaction.atomic
def update_term(user, kind, term_id, *, name, is_available):
    """Rename a term or withdraw it, and return it.

    Both in one call, because the screen holds both and because withdrawal is
    not a different kind of act here: ``is_available`` is a column on the same
    row, and clearing it is what stands in for a delete. Every strain already
    carrying the term keeps it -- see the module docstring.

    A rename takes the slug with it, because ``SlugFromName.save`` derives it on
    every write. So renaming "citrus" to "citrusy" is refused if "citrusy" is
    already in the list, by the same rule that refuses adding it twice.
    """
    _authorise(user)

    model = _term_model(kind)
    term = model.objects.get(pk=term_id)
    term.is_available = is_available
    _apply_term(model, term, name=name, creating=False)
    return term


def _term_model(kind):
    """The model behind a URL segment, or ``KeyError`` for an unknown one.

    The endpoint turns the ``KeyError`` into a 404. A path that names neither
    vocabulary is a path with nothing behind it, which is what a 404 says.
    """
    return TERM_MODELS[kind]


def _apply_term(model, term, *, name, creating):
    """Validate and write one vocabulary entry.

    The same shape as ``_apply`` and the same reason for existing: uniqueness is
    on the derived slug, which ``full_clean`` will not check because the column
    is not editable, so the refusal has to be raised here to be reported against
    ``name``.
    """
    trimmed = (name or '').strip()
    errors = {}

    if not trimmed:
        errors['name'] = ['This term needs a name.']
    else:
        slug = slugify(trimmed)[:40]
        if not slug:
            errors['name'] = [
                'That name has no letters or numbers in it, so the list has '
                'nothing to key it on.'
            ]
        else:
            taken = model.objects.filter(slug=slug)
            if not creating:
                taken = taken.exclude(pk=term.pk)
            if taken.exists():
                errors['name'] = [f'“{trimmed}” is already in the list.']

    term.name = trimmed

    try:
        term.full_clean(exclude=('name',))
    except ValidationError as error:
        _merged(errors, error)

    if errors:
        raise ValidationError(errors)

    term.save()
    return term

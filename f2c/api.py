"""The API root: one NinjaAPI instance, and the routers each feature mounts on it.

This module belongs to the project rather than to any app, because it is the one
place that has to know about all of them. Each feature owns its own router and
schemas -- ``authn.api``, ``documents.api`` -- and nothing here reaches into
them beyond mounting the router they expose. Adding a feature means adding one
``add_router`` line.

Endpoints require a valid session by default; the handful that cannot (health,
sign-in, the club documents a visitor reads before an account exists) opt out
with ``auth=None``. django-ninja's cookie auth also enforces CSRF on unsafe
methods, which is mandatory here because authentication is cookie-based rather
than token-based.
"""
from app.core.accounts.api import router as accounts_router
from app.core.accounts.registration_api import router as customers_router
from app.core.authn.api import router as authn_router
from django.conf import settings
from app.core.documents.api import router as documents_router
from app.club.membership.administration_api import router as member_admin_router
from app.club.membership.api import router as membership_router
from app.core.payments.api import router as payments_router
from app.club.strains.api import router as catalogue_router
from ninja import NinjaAPI, Schema
from ninja.security import django_auth

api = NinjaAPI(
    title='Cultivators Collective API',
    version='1.0.0',
    description='JSON API consumed by the Next.js frontend.',
    auth=django_auth,
    docs_url='/docs' if settings.DEBUG else None,
)

# A member's own profile: the fields they may change, the two they may only
# read, and their photograph. Every endpoint is about request.user and none
# takes an account identifier -- see accounts/api.py on why that is the design
# rather than an omission. /accounts/me/avatar is the only endpoint on this API
# that answers with something other than JSON.
api.add_router('/accounts', accounts_router)
# Creating a store account. Unauthenticated for the same reason /members/register
# is -- there is no account until it returns -- and mounted on its own prefix
# rather than beside the profile endpoints above, so an auth=None route is not
# filed next to the ones that read a member's own record. A customer is a `User`
# with no other row, which is why this lives in `accounts` and not in a market
# app: see `accounts/registration.py`.
api.add_router('/customers', customers_router)
# Passkeys, emailed codes and sessions.
api.add_router('/auth', authn_router)
# Club documents. /documents/current is unauthenticated: sign-up has to read it
# before an account exists.
api.add_router('/documents', documents_router)
# Joining. /members/register is unauthenticated for the same reason: there is
# no account until it returns.
api.add_router('/members', membership_router)
# The same prefix, a second router, and the split is deliberate: joining the
# club is unauthenticated and administering the register holds out for
# `platform.disable_user`, checked in `membership.administration` rather than by
# the router. One module carrying both would put an `auth=None` endpoint two
# screens away from one that reads a member's identity number. See
# `membership/administration_api.py`.
api.add_router('/members', member_admin_router)
# Membership subscriptions. Both endpoints are unauthenticated and neither
# could be otherwise: a member cannot sign in until their membership is paid
# for, and Payfast has no session to present when it notifies.
api.add_router('/payments', payments_router)
# The strain catalogue, administrator-curated and platform-wide. Every endpoint
# holds out for `platform.manage_strain_catalogue`, checked in
# `strains.services` rather than by the router -- so the member-facing browse in
# Block 5 will be a second router over the same models rather than a relaxation
# of this one. Mounted at /catalogue rather than /strains because the router
# also owns the aroma and effect vocabularies, which are not strains.
api.add_router('/catalogue', catalogue_router)


class HealthOut(Schema):
    """Declared here rather than in a feature app: the probe belongs to no
    feature, and a module of its own for three fields would only hide it."""

    status: str
    debug: bool


@api.get('/health', response=HealthOut, tags=['meta'], auth=None)
async def health(request):
    """Unauthenticated liveness probe, also used by the frontend smoke test."""
    return {'status': 'ok', 'debug': settings.DEBUG}

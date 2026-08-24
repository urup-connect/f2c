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
from app.authn.api import router as authn_router
from django.conf import settings
from app.documents.api import router as documents_router
from app.membership.api import router as membership_router
from app.payments.api import router as payments_router
from ninja import NinjaAPI, Schema
from ninja.security import django_auth

api = NinjaAPI(
    title='Cultivators Collective API',
    version='1.0.0',
    description='JSON API consumed by the Next.js frontend.',
    auth=django_auth,
    docs_url='/docs' if settings.DEBUG else None,
)

# Passkeys, emailed codes and sessions.
api.add_router('/auth', authn_router)
# Club documents. /documents/current is unauthenticated: sign-up has to read it
# before an account exists.
api.add_router('/documents', documents_router)
# Joining. /members/register is unauthenticated for the same reason: there is
# no account until it returns.
api.add_router('/members', membership_router)
# Membership subscriptions. Both endpoints are unauthenticated and neither
# could be otherwise: a member cannot sign in until their membership is paid
# for, and Payfast has no session to present when it notifies.
api.add_router('/payments', payments_router)


class HealthOut(Schema):
    """Declared here rather than in a feature app: the probe belongs to no
    feature, and a module of its own for three fields would only hide it."""

    status: str
    debug: bool


@api.get('/health', response=HealthOut, tags=['meta'], auth=None)
async def health(request):
    """Unauthenticated liveness probe, also used by the frontend smoke test."""
    return {'status': 'ok', 'debug': settings.DEBUG}

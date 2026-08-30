"""A deploy check for the one Payfast setting a proxied deployment gets wrong.

``DJANGO_BEHIND_PROXY`` decides where ``notification_source_ip`` reads the
caller's address from -- one variable for one deployment fact, shared with
``SECURE_PROXY_SSL_HEADER``, with ``DJANGO_PAYFAST_BEHIND_PROXY`` left as an
override. It is off by default for a good reason:
``X-Forwarded-For`` is a request header like any other, so trusting it when
nothing overwrites it lets a caller prepend an address of their choosing and
walk straight through the source check. Opt-in is the right default and it is
not the right *value* for any deployment that sits behind a load balancer --
which, on Azure Container Apps, App Service, or anything with ingress in front
of it, is all of them.

**What makes this worth a check rather than a line in a runbook is the shape of
the failure.** Nothing raises at startup. Nothing fails a smoke test. Members
sign up, reach Payfast, pay, and come back to a return URL that says thank you,
because the return URL is the browser's redirect and has nothing to do with the
notification. Meanwhile every server-to-server notification arrives with
``REMOTE_ADDR`` set to the ingress proxy, fails ``source_is_payfast``, and is
answered 400. Payfast retries and gives up. No membership is ever activated, the
money is taken, and the only evidence is a warning in a log nobody is reading
yet -- ``design/features/payments.md`` calls the notification "the only thing
that activates a membership", and this is the setting that switches it off.

It is a ``Warning`` rather than an ``Error`` because a Django exposed directly
to the internet with no proxy in front of it is a legitimate deployment, and for
that one ``behind_proxy=False`` is correct. ``manage.py check --deploy`` is
where it surfaces, which is a Block 0 item in its own right.
"""
from django.conf import settings
from django.core.checks import Tags, Warning, register


@register(Tags.security, deploy=True)
def check_payfast_reads_the_forwarded_address(app_configs, **kwargs):
    """Warn when a deployed Payfast endpoint will read the proxy's address.

    Skipped under ``DEBUG``, where the notification endpoint is reached by
    ``manage.py payfast_notify`` from localhost and there is no proxy to speak
    of.
    """
    if settings.DEBUG or settings.PAYFAST.behind_proxy:
        return []

    return [
        Warning(
            'DJANGO_BEHIND_PROXY is not set, so the Payfast notification '
            'endpoint will read REMOTE_ADDR.',
            hint=(
                'If anything terminates TLS in front of Django -- Azure '
                'Container Apps ingress, App Service, a load balancer, a CDN '
                '-- REMOTE_ADDR is that proxy and not Payfast, so every '
                'notification fails the source-address check and is answered '
                '400. Checkout still succeeds and the member is still charged; '
                'the membership is simply never activated. Set '
                'DJANGO_BEHIND_PROXY=true -- the same variable Django uses for '
                'SECURE_PROXY_SSL_HEADER, because it is the same fact about the '
                'deployment -- and make sure the edge overwrites X-Forwarded-For '
                'rather than appending to it. DJANGO_PAYFAST_BEHIND_PROXY '
                'overrides it for the case where the edge terminates TLS but '
                'does not overwrite the header. Ignore this only if Django is '
                'reached directly.'
            ),
            id='payments.W001',
        )
    ]

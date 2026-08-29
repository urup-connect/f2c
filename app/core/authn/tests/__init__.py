"""Tests for the sign-in surface, split by the layer under test.

``test_api`` covers the HTTP endpoints -- which credential each address is
offered, what a forged or replayed ceremony gets, and that a non-Active account
is refused identically to an unknown one. ``test_otp`` and ``test_webauthn``
cover the two credential services beneath it, and ``test_throttles`` covers the
per-IP limits on the endpoints that run before a session exists.
"""

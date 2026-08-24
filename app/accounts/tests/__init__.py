"""Tests for the member record and the admin over it.

``test_models`` covers what the record guarantees: an email address that is one
identifier however it is typed, an ``is_active`` that cannot drift from
``status``, an ID number that round-trips through encryption, and an erasure
that clears everything it promises to. ``test_admin_forms`` covers the write-only
ID-number field, which is the one place staff can set a value they can never
read back.

The RSA ID number both use comes from ``common.tests``.
"""

"""Tests for the shared primitives: encryption and RSA ID-number checks.

Neither has a model or an endpoint, so both are tested directly. They are the
foundation the member record is built on -- an encrypted column that silently
stops round-tripping loses data with no error -- which is why they are tested
here rather than only through the code that calls them.

A note on the shared constant below. Several suites across several apps need a
structurally valid RSA ID number and it is the same one everywhere, so it lives
beside the validators that define what makes it valid.
"""

# 1 January 1980, citizen, correct Luhn check digit.
VALID_SA_ID = '8001015009087'

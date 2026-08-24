"""Project-level tests: the things that belong to no single feature.

So far that is the brand skin over the Django admin, which is a matter of static
files and template overrides rather than of any app's models. It lives here for
the same reason ``cultivatorscollective/api.py`` does: it spans the project, and
filing it under one feature app would make it look like that feature's concern.
"""

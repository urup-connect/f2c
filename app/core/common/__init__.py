"""Primitives shared by more than one feature, and owned by none of them.

Nothing in here has models, endpoints or admin views. It is the layer the
feature apps sit on: encryption (``crypto``), South African identity-number
checks (``validators``) and the one response shape every feature returns
(``schemas``).

The rule for putting something here is that at least two features need it and
neither should own it. ``crypto`` qualifies because a member's ID number is not
the only thing this project will ever encrypt; ``validators`` because the same
ID number is checked at sign-up, in the admin and on the member record.
"""

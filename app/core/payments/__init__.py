"""Membership subscriptions, and the Payfast integration behind them.

This app owns the money. It knows what a membership costs, what a member has
paid for, and what a payment does to an account -- and it is the only place
that talks to Payfast.

``accounts`` is the only app it depends on, and nothing depends back except
``membership``, which opens a subscription at the end of a registration. See
``models`` for the two rows, ``gateway`` for the Payfast protocol, and
``services`` for the rules that join them.
"""

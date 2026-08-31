# Payments

A membership subscription, billed by Payfast, and the notification that turns a paid subscription
into an account that can sign in.

## 1. Executive summary

**A payment is now what activates a membership.** Before this, `POST /api/members/register` left a
member at `pending_payment` and nothing moved them off it but a member of staff in the Django
admin. `app/core/payments` closes that gap: registration opens a subscription in the same transaction
that writes the member, the member is handed to Payfast, and the server-to-server notification
Payfast sends back is what calls `User.activate()`.

The arrangement is a **recurring subscription**, not a joining fee. Payfast holds the mandate
(`subscription_type=1`) and bills on its own schedule; this application does not run a billing job,
because it has nowhere to run one. What it does own is the price at the moment a member agreed to
it, the record of every payment, how far the membership is paid up, and the decision to withdraw
access when that date passes.

Four properties are load-bearing and each has its own section below.

1. **Only the notification activates an account.** Not the member's return from Payfast, which is a
   browser redirect they control and can replay. Section 3.
2. **A notification passes four independent checks** — source address, merchant, signature, and a
   callback asking Payfast whether it sent this — before it is allowed to change anything.
   Section 3.2.
3. **Applying a notification twice does nothing twice.** Payfast retries; the retry carries the same
   payment id, and a unique index makes the second delivery a no-op. Section 3.3.
4. **The checkout carries no personal data at all.** Not the member's name, address or mobile
   number, and Payfast requires none. Section 5.2.

**One existing decision is deliberately narrowed, and it is the most important thing in this
document.** Sign-up answered a duplicate submission — an address, identity number or mobile already
on file — *identically* to a new registration, so that the form could not be used to ask whether a
named person belongs to a cannabis club. Redirecting a new member straight to Payfast breaks that,
because a duplicate has no subscription to pay for. Section 4 sets out what now differs, what is
still identical, what the disclosure is bounded to, and the option that was weighed and not taken.

Two things are **not built** and are not oversights: nothing schedules the lapsing command, and no
member-facing screen shows subscription status or offers cancellation. Section 9.

## 2. Why Payfast, and why a subscription

Payfast and PayGate were both candidates in `design/plan.md`. Payfast was chosen on integration
cost: a signed form POST to its payment engine and a notification back, with a published sandbox
merchant that needs no onboarding call, against PayGate PayWeb3's three-step initiate/redirect/notify
and a merchant account that has to exist before anything can be tested. The two are separate
products despite Payfast having acquired PayGate in 2021, and nothing here is shared between them.

`app/core/payments/gateway.py` is the only module that knows the Payfast protocol. Swapping gateways
means writing a second one of it; nothing in `services`, `models` or `api` names Payfast except
where it names the notification endpoint.

`subscription_type=1` — a Payfast subscription — rather than `2`, tokenised ad-hoc billing. The
difference is who initiates each charge. With a subscription, Payfast does, on a schedule it holds;
with ad-hoc billing this application would be responsible for a billing run, a retry policy and a
scheduler. There is no scheduler in this deployment, which is the same reason section 9 records the
lapsing command as unscheduled.

The price and the cycle are read from the environment, one variable each, rather than from an
admin-managed plan table. Changing the fee is a deploy. That was the explicit choice: everything
else in this project is configured the same way, and a fee model with effective dates and history is
a feature to build when somebody needs to change a price without one.

## 3. What activates a membership

### 3.1 The notification, and nothing else

Payfast tells this application about a payment twice, over two entirely different channels, and only
one of them counts.

The member's browser is redirected to `return_url` when they finish. That is a **GET the member
controls**: they can bookmark it, replay it, share it, or arrive at it having paid nothing. So
`/signup/paid` reads nothing, looks nothing up, and does not tell the member their membership is
active — it says the payment is being confirmed, which is the only thing being on that page proves.

`notify_url` is a **server-to-server POST from Payfast**. That is the transaction. It is the only
thing that writes a `Payment` row, extends `paid_until`, or calls `User.activate()`.

Getting this the wrong way round is the classic payment-integration vulnerability, and it is worth
being explicit about why: a member who reaches `/signup/paid` by typing the URL has proved nothing
at all, and a `return_url` handler that activated an account would hand out free memberships to
anyone who read the address bar once.

### 3.2 The four checks

`gateway.verify_notification` runs the three that need no network, and
`services.apply_notification` adds the fourth. They run in order of cost, so a forged notification
never causes an outbound call.

| Check | Refuses | Why the others do not cover it |
| --- | --- | --- |
| Source address | Anything not resolving from one of Payfast's four notification hosts | The signature alone does not bind a notification to Payfast: the passphrase travels to Payfast on every checkout, so anyone who ever learns it can sign one |
| Merchant | A notification for another merchant id | A shared or mistyped `notify_url` would otherwise apply somebody else's payments to our subscriptions |
| Signature | A body that was tampered with | Without it the amount and the payment status are attacker-chosen values |
| Callback | Anything Payfast does not confirm sending | The only check that asks the other party. It is what makes a leaked passphrase insufficient on its own |

The hosts are **resolved at verification time rather than pinned as a list of IP addresses**.
Payfast changes them without notice, and a stale list fails closed — every notification rejected,
every membership stuck at Pending payment, and nothing in the logs naming the cause. Resolution
failures are swallowed per host so one unreachable resolver cannot reject everything; if all four
fail the set is empty and the check says no, which is the safe direction.

The signature is **order-sensitive, and the two orders are different**: a checkout is signed in
Payfast's documented field order, a notification in the order its fields arrived. That is why the
notification endpoint reads the raw request body with `parse_qsl` rather than using `request.POST` —
a `QueryDict` has already collapsed duplicates and lost the only ordering that verifies. It is also
why the encoding matches PHP's `urlencode` rather than Python's `quote_plus`: spaces become `+`, hex
escapes are upper case, and `~` is escaped, which `quote_plus` does not do.

Two smaller rules sit alongside them. **The amount is checked to the cent against
`subscription.amount`** — the price copied onto the row when the member agreed to it — and never
against the configured price, because raising the fee would otherwise turn every existing member's
next renewal into an amount mismatch. And **an unrecognised `payment_status` is refused rather than
mapped to the nearest known one**, because a status Payfast adds later and this code guesses at is
how an account gets activated by an event that did not mean that.

The refusal reason is logged and never returned. Telling a caller which check failed tells an
attacker which one to fix next.

### 3.3 Status codes are the contract

Payfast decides whether to redeliver from the status code, so a wrong one is not cosmetic.

| Code | When | What Payfast does |
| --- | --- | --- |
| 200 | Applied, or already applied | Stops retrying |
| 400 | Rejected finally — bad signature, unknown subscription, wrong amount | Gives up after its own retries; nothing would fix it |
| 503 | Payfast could not be reached to confirm | Retries, which is what should happen |

The 400/503 split is the one worth guarding. A 400 where a 503 belongs drops a real payment on the
floor and leaves a member who paid unable to sign in; a 503 where a 400 belongs asks Payfast to
retry a forgery forever. `confirm_with_payfast` returns `None` rather than `False` for a network
failure precisely so that "Payfast says no" and "we could not ask" reach different branches.

Idempotency rests on a unique index on `Payment.gateway_payment_id`. `get_or_create` handles the
ordinary retry and the `IntegrityError` branch handles the concurrent one — Payfast can deliver
twice at once, and two workers can both find nothing before either writes. A duplicate answers 200
and changes nothing; without that, a redelivered notification would grant a second cycle of
membership free, silently, with every response still looking correct.

## 4. The duplicate-registration disclosure

This section records a decision that reverses part of `features/sign-up.md`.

**The rule as it stood.** `register_member` answers a submission naming an address, identity number
or mobile already on file exactly as it answers a new registration, and writes nothing. The reason
is in that document and in `app/club/membership/services.py`: the alternative turns the sign-up form into
a way to ask whether a named person is a member of a cannabis club, which in South Africa is
sensitive information about a private individual.

**Why the redirect breaks it.** A new member gets a checkout token and goes to Payfast. A duplicate
cannot get one: there is no subscription to pay for, and handing back a token for the *existing*
member's subscription would let a stranger pay for somebody else's membership and confirm the
address outright. So the two paths cannot end on the same screen.

**What was chosen.** Redirect a new registration straight to Payfast; answer a duplicate with the
neutral confirmation screen and email the outstanding payment link to the address instead.

**What is still identical.** The status code, the `status`, and the `detail` sentence. Nothing is
written. No name, join date, account status or outstanding amount comes back. The response differs
in exactly one field — `checkout_token` is null — and `DuplicateTests` in
`app/club/membership/tests/test_api.py` asserts that field-by-field rather than asserting the bodies
match, so the size of the disclosure is pinned by a test rather than described here and trusted.

**What leaks.** One bit, to whoever submitted the form: *this address may already be on file*. Not
confirmed — a member who registered and abandoned the payment, and a genuinely new address whose
registration failed, both reach the confirmation screen too. And the three duplicate keys still
answer identically to each other, so the form cannot be used to ask *which* of address, identity
document or handset a value matched, which was always the sharper question.

**The option not taken.** Email every member their payment link and send nobody to Payfast directly.
That preserves the original rule completely, and it was declined for conversion: it puts an email
round-trip between a completed form and a payment, and it depends on the real email provider
`MAILERS` still does not have. The trade is recorded as risk 1 rather than presented as costless.

**One narrower rule inside the fallback.** The email is sent only when the duplicate was matched
**on the address**. A submission that duplicates an identity number or a mobile while naming a
different address gets no email at all — sending one would tell the typed address about somebody
else's membership, which is a worse disclosure than the one this section is about.

## 5. The hand-off to Payfast

### 5.1 Two routes, one screen

`/pay` reads the token from an `httpOnly` cookie the registration action set. `/pay/[token]` reads
it from the path, which is what an emailed link can carry. Both render the same component.

The cookie exists because **a server action can only redirect, and a redirect carries only a URL**.
Putting the token in the query string would work and was refused: a URL is written to every access
log between the member and this application, kept in browser history, and sent in `Referer` to
anything the next page loads. `SameSite=Lax` rather than `Strict`, because the member returns from
Payfast on a cross-site redirect and `Strict` would withhold the cookie exactly then.

The emailed link has no such option, which is why the token is 32 bytes of entropy, lives a day
rather than indefinitely, and is **spent the moment the subscription is paid** — a link found in an
inbox later resolves to "no longer valid" rather than starting a second mandate.

Three outcomes, three screens, and the split between the last two matters: an expired or already-paid
token is the member's to fix by getting a fresh link, while an unreachable API is our fault. Telling
a member their link had expired because our own API was down would send them chasing a link that was
never the problem. Our own failures mint an eight-character reference, log the cause against it, and
show only the reference — the same treatment a failed registration gets.

### 5.2 The checkout carries nothing about the member

Payfast accepts `name_first`, `name_last`, `email_address` and `cell_number` and requires none of
them. None is sent.

The reason is that the field set is fetched over a URL with a bearer token in it. A payload naming
the member would make that token a way to *read personal data* rather than a way to pay, and the
token appears in an emailed link. So what crosses is the merchant's own identifiers, the price, and
`m_payment_id` — the subscription's UUID, which names a row and says nothing about who holds it.
The member types their own details on Payfast's page, which is where the card is typed anyway.

The cost is a slightly longer checkout with no prefill, and it is a real conversion cost. It is
taken because this is the project that will not put a nickname in a query string; making the
payment endpoint the one loose surface would be inconsistent to the point of pointlessness.
`test_it_carries_no_personal_data_at_all` and `test_it_carries_nothing_about_the_member` hold it.

### 5.3 The form does not submit itself

An earlier version of `PayfastForm` auto-submitted on mount, on the reasoning that a member who has
just filled in a form should not need another click. That was wrong here, and the reversal is worth
recording because the first instinct is the common one.

This is the screen where a **recurring debit mandate** is agreed to. Auto-submitting puts the amount
and the sentence "Payfast will bill it until you cancel" on screen for a few milliseconds before the
browser leaves. A member is entitled to read what they are agreeing to be charged, repeatedly,
before agreeing to it — and under the Consumer Protection Act that is more than courtesy. So the
button is the member's, the recurring terms sit *above* it rather than below, and pressing it is the
consent.

Dropping the auto-submit also made the component a Server Component with no state, no effect and no
client bundle — so the screen behaves identically with JavaScript on and off, rather than having a
JavaScript path plus a fallback that only one of them ever exercises.

Every field is rendered exactly as Django built it: no sorting, trimming, filtering or additions.
Payfast signs the checkout over that precise set, and it answers a failed signature with a generic
decline naming nothing, so a "tidied" field set is a bug with no diagnostic.

### 5.4 The copy exemptions

`copy-compliance.ts` reserved two exemptions for the payment screens before they existed. Only one
is taken.

`CURRENCY` is exempt: the screen has to name an amount. `RETAIL_VOICE` was expected to be exempt too
and is **not** — "subscription", "payment" and "Payfast" ask to be paid without a single word from
that pattern, so the corpus is held to the rule and `payment-content.test.ts` asserts it. The
reservation is left recorded in that module because the reasoning that produced it is worth having
beside the outcome that disproved it.

`CLINICAL_CLAIM` and `ELIGIBILITY_CLAIM` apply in full. The second matters *more* here than
elsewhere: this is the screen a member reaches after giving an identity number, and it is the
likeliest place for somebody to add a reassuring sentence about who may join.

No copy string holds a price. The figure on screen is formatted from the signed `amount` field being
posted, so what is displayed and what is charged cannot disagree.

## 6. The two rows

`Subscription` is the standing arrangement; `Payment` is one movement of money against it. The same
split `documents` makes between a document and its revisions.

**The price and cycle are copied onto the subscription when it is opened**, not read back from
settings when they are needed. A member who joined at one amount is on that amount; changing the
configured price must change what new members are asked for and nothing about what existing ones
agreed to. Reading the setting later would silently rewrite every past arrangement — and would make
a renewal at the agreed price look like fraud to the amount check in section 3.2.

**The subscription's primary key is what Payfast is told.** It travels as `m_payment_id` and returns
on every notification, which is how a notification is matched to a member. A UUIDv7 is safe to hand
over: it names a row and says nothing about who holds it, and that is the property that lets the
checkout carry no personal data.

**The checkout token is separate from the primary key.** The key goes to Payfast; the token goes in a
URL a member follows. Keeping them apart means the value in the address bar is not the value in
Payfast's dashboard, and it can be expired and re-minted without touching the mandate.

**No notification is stored verbatim.** A Payfast notification carries the name, email address and
mobile number the member typed on Payfast's page, and keeping the raw body would quietly re-import
personal data this application went to some trouble not to send. Only the amounts, the status and
the two identifiers are copied off it. The cost is that a dispute cannot be re-litigated from our
own audit trail — Payfast's dashboard is the other half of the record — and that is the same trade
made everywhere else here.

Two constraints are in SQL rather than in `save()`, so a data migration, a repair script or a raw
`UPDATE` is held to them too:

- **`one_live_subscription_per_member`**, a partial unique index over pending and active
  subscriptions. Two live mandates against one account is Payfast billing twice. Cancelled and
  lapsed rows are excluded, so a member who cancelled and rejoined has a history rather than a
  conflict.
- **`active_subscription_is_paid_up`** — an active subscription has a Payfast token and a
  `paid_until`. The lapsing query trusts `paid_until`, and a null there would silently exempt an
  account from ever lapsing.

`Payment.subscription` is `PROTECT`. Deleting a subscription does not unmake a payment; it only makes
the next reconciliation unexplainable.

## 7. Lapsing, and what a cancellation does not do

**A cancellation does not switch anybody off.** Payfast's `CANCELLED` notification ends the mandate
and stamps `cancelled_at`; the account stays active until `paid_until` passes. Cutting access on the
cancellation would take back time the member has already paid for, which is both wrong and, under
the Consumer Protection Act, not ours to take.

**A failed charge does not either.** Payfast retries a failed recurring charge on its own schedule,
so acting on the first failure would cut off a member over a card that is about to be replaced. The
failure is recorded and nothing else.

So the withdrawal of access is **computed from `paid_until` rather than driven by an event**, which
is the only thing that covers both a cancelled mandate and a card that quietly stopped working —
neither of which sends a notification saying "this member should now be switched off".
`manage.py lapse_memberships` is that computation. It sets the subscription to `LAPSED` and calls
`user.deactivate()`, which blocks sign-in, cuts live sessions, erases nothing, and is reversed by
paying again. It touches no account that is not currently Active, so a suspension staff applied for
some other reason is not quietly relabelled "did not pay".

`--dry-run` reports and changes nothing, and is tested as carefully as the real run.

## 8. Development

Payfast delivers notifications server-to-server and **cannot reach a localhost `notify_url`**, so the
one step that activates a membership is the one step that never fires on a developer's machine. The
same shape of problem as the console email backend, and the same kind of answer:

```
manage.py payfast_notify --email someone@example.com
manage.py payfast_notify --email someone@example.com --status CANCELLED
```

It is not a shortcut past the verification. The payload is signed with the configured passphrase and
goes through `services.apply_notification` exactly as a real notification does, so a signature bug
shows up here rather than in production. Two checks are stood down and both are about the network
rather than the payload: the source address is asserted, and the callback to Payfast is skipped
because Payfast did not send this.

It **refuses to run with `DEBUG` off**. A command that can activate a membership from a shell has no
business existing in production, where the honest route is *Activate selected accounts* in the member
admin — which records an account change and claims no payment.

With no merchant configured and `DEBUG` on, `payfast_config` falls back to Payfast's published
sandbox merchant, so the whole flow works on a fresh clone. With `DEBUG` off every variable is
required and Django refuses to start: a payment integration that silently falls back to a sandbox is
one that takes a member's money into an account nobody is watching. **Live is never the default** —
`DJANGO_PAYFAST_SANDBOX` unset means sandbox in every environment, so a deployment reaches the live
engine only by asking for it.

## 9. What is not built

- **Nothing schedules `lapse_memberships`.** Until something does, an unpaid membership keeps its
  access indefinitely. A daily cron or an App Service WebJob is the intended home. Risk 2.
- **No member-facing subscription screen.** A member cannot see what they pay, when it renews, or
  what they have paid, and cannot cancel from this application — cancellation is done in Payfast or
  by asking the club. The authenticated frontend is written but not routed
  (`frontend.md` §9), so there is nowhere to put it yet.
- **No email when a membership is activated, lapses, or fails to renew.** The copy on `/signup/paid`
  promises one, and nothing sends it. **The mail plumbing is no longer the obstacle** — a provider is
  configured for both storefronts and the club mailbox authenticates (P1) — so what is missing here
  is the three messages themselves, not somewhere to send them from. `accounts.notifications` is the
  pattern to follow: on-commit, per storefront, and a send failure logged rather than raised.
- **No refunds, no proration, no plan changes.** A price change applies to new members only, and
  there is no path for moving an existing member onto a different amount.
- **No reconciliation report.** Payments are recorded and visible in the admin; nothing totals them
  against a Payfast statement.
- **`amount_fee` and `amount_net` are stored and never used.** They are recorded because a
  reconciliation will need them and because they cannot be recovered later.

## 10. Risks

| # | Risk | Consequence | Position |
| --- | --- | --- | --- |
| 1 | A duplicate registration reaches a different screen from a new one | Somebody submitting another person's address learns it may already be on file — a partial reversal of the non-disclosure rule in `sign-up.md` | Accepted, and bounded: one field differs, nothing is confirmed, and the three duplicate keys still answer identically to each other. The alternative — emailing every member their link — was weighed and declined for conversion. Revisit if the club treats membership as more sensitive than the conversion is worth |
| 2 | Nothing runs `lapse_memberships` | An unpaid or cancelled membership keeps its access indefinitely | Open. The command and its tests exist; the schedule does not. This is the largest functional gap in the feature |
| 3 | No real email provider | The emailed payment link — the entire duplicate-registration fallback — is printed to a console and reaches nobody | Open, and shared with sign-in codes. Until `MAILERS` is real, a duplicate registration has no route to payment at all |
| 4 | `X-Forwarded-For` is read when `DJANGO_PAYFAST_BEHIND_PROXY` is set | If the edge appends to that header rather than overwriting it, a caller can prepend a Payfast address and defeat the source check | Mitigated by making it opt-in per deployment and documenting the requirement. The signature and the Payfast callback still stand behind it, so defeating one check is not sufficient |
| 5 | MD5 signatures | The digest is weak | Not ours to choose: it is what Payfast computes, so it is what verifies. The integrity of the exchange rests on the passphrase and on the callback in section 3.2, not on the digest |
| 6 | The notification endpoint is unthrottled | A burst of requests reaches the verification logic | Deliberate. It already refuses every caller that is not one of Payfast's notification hosts, which is tighter than any rate. A limit there would drop *real* notifications on the first of the month, when every monthly subscription renews at once — and a dropped notification is a member who paid and cannot sign in |
| 7 | A payment against an account that is Pending verification or erased | Money taken with no membership activated | Recorded rather than refused, and logged at WARNING for a human. Refusing the notification would make Payfast retry forever and would lose the money's trail |
| 8 | No notification is stored verbatim | A dispute cannot be reconstructed from our own records | Accepted, for data minimisation: the raw body carries personal data this application deliberately does not send. Payfast's dashboard is the record for a dispute |
| 9 | The cycle length is nominal, not calendar-exact (31, 93, 184, 366 days) | `paid_until` drifts from the true billing date over many cycles | Accepted, and it errs long by design — a membership is never cut off before the day it is paid to. Every renewal extends from `paid_until` rather than from today, so the drift does not compound into lost access |
| 10 | A checkout token in an emailed URL | Anyone with the mailbox, or with a log of that URL, can pay the subscription | Bounded: it buys the member a membership they applied for and reveals nothing about them, it expires in a day, and it is spent on payment. The cookie route exists precisely so this is the exception rather than the norm |

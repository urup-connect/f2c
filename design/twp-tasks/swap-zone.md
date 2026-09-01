# Swap Zone

## Leaf Rating
Plants in the swap zone should not show cost in Rands. Any plant entering the swap zone (loading by cultivator sharing member or put up for swap by member) should display its leaf rating.

Leaf rating is calculated by using the grow price divided by 1000 and rounded to nearest 0 or .5 decimal. ROUND((GrowP/1000),0.5)
examples:
* Grow price is R500, leaf rating is 0.5
* Grow price is R850, leaf rating is 1
* Grow price is R1100, leaf rating is 1
* Grow price is R1650, leaf rating is 1.5
* Grow Price is R1900, leaf rating is 2

When swapping, the members swap offer and swap request must have equivalent swap value, or the member can acknowledge that their request value is lower than their offer and they choose to forfeit the difference.

Question:
- [x] A grow price under R250 rounds to a leaf rating of **0.0**, which has no swap value at all.
      `swap-zone` sets no floor and its cheapest example is R500. Decide before Block 10 relies on it
    I’ve only heard pricing of around R1000, so I don’t think this will be an issue

**Answered.** Pricing sits around R1,000, so a grow price under R250 is not expected. The rule is
therefore the one that keeps an unexpected price harmless rather than the one that prices it:

- A leaf rating **floors at 0.1**. No plant ever rates 0.0.
- 0.1 is deliberately not a multiple of 0.5, so a rating below swap value is recognisable as one
  wherever it is read, and a R50 plant is not promoted to the same 0.5 as a R250 one.
- A plant rating under 0.5 — one whole step — **may not enter the swap zone**. It has no swap value
  for an offer or a request to be equivalent to. The refusal is an error a member is shown, not a
  silent exclusion: `Plant.assert_swappable` raises with the code `below_swap_value`, and
  `Plant.objects.swappable()` excludes the plant from any match.
- The plant is still perfectly saleable in Rands. This is a swap-zone rule and nothing else.

## Maturity, and what equivalent value cannot arbitrate

Question:
- [x] Leaf rating derives from grow price alone, so **maturity is not in it**. A plant three weeks from
      harvest and a seedling of the same grow price carry the same rating, and equivalent-value
      matching prices a real difference at zero. Everyone wants the mature side of that trade.

**Answered — C17. The formula above does not change.** A maturity multiplier was the obvious fix and
it loses on three counts: the rating is defensible precisely because it is a rounding of a **disclosed
grow price** and a member can reproduce it; a multiplier moves every day the plant is alive, so the
stored rating, the 0.1 floor and the 0.5 swap minimum stop being answerable in a query; and it would
not have arbitrated anyway — it reprices the mature plant without deciding which member gets it.

The rule instead:

- A swap for a **mature** plant is a **request the current holder confirms**, not an instant swap. For
  a sharing member's plant the confirmer is the cultivator, who offers it on that person's behalf; a
  sharing member does not transact.
- Everything else swaps instantly. This is the member story's existing instant/confirmed distinction,
  restated on the **plant** rather than on the kind of owner — the swap zone must match on plants and
  their owners and never on owner *type*, so that the sharing-member role can be retired later without
  changing the matcher.
- A request **holds** the offered plant rather than transferring it, so one plant cannot sit in two
  live requests. A request nobody answers **lapses** and the offer returns to the zone. A decline is
  allowed and is recorded.
- **Where "mature" starts is still to be set** — harvested stock always, and the recommendation for
  the rest is within 21 days of the estimated harvest date. It is the dial between an instant path
  that exists and one that does not: a sharing member's four plants are *flowering* plants, so a
  threshold set at "in bloom" would make every swap in the zone a confirmed one.

The equivalence rule and the forfeit-the-difference acknowledgement above are unaffected.

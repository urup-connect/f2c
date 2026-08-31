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

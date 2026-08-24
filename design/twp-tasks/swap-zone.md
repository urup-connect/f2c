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

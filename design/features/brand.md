# Brand design system

Colour, typography, logo artwork and photography, derived from the 2026 brand guidelines deck and
expressed as Tailwind v4 design tokens.

## 1. Executive summary

The brand is implemented as tokens in one file — `app/globals.css` — and every screen reaches colour
and type through semantic aliases rather than through raw hex values. A palette change is then a
change to that file.

Three decisions in here are not cosmetic and are worth a decision-maker's attention.

**Two tokens are not from the brand.** The deck supplies no error colour and no dark palette. Both
gaps are filled with something explicitly marked as a placeholder, in a way that makes replacing it a
one-value change. Section 4 sets out what the brand still owes.

**The logo and photography assets carry their own constraints in code.** Each photograph declares the
largest CSS width it may be rendered at, and a component refuses a wider request at the call site.
The deck's photographs are small, and the failure mode is not that they look bad today — it is
somebody reusing one in a hero later.

**One photograph from the deck is deliberately absent.** The deck includes a photograph of a
cultivator's face. Publishing an identifiable person needs their consent and the deck records none.

## 2. Palette

The printed swatches from the guidelines deck:

| Token | Value | Role |
| --- | --- | --- |
| `--color-forest-green` | `#1F3B2D` | Primary |
| `--color-forest-green-deep` | `#0F1C13` | Deepest green |
| `--color-olive-green` | `#7BA05D` | Accent |
| `--color-sage-green` | `#C7D9B0` | Borders |
| `--color-cream-warm` | `#F9F1E8` | Page background |
| `--color-cream-cool` | `#F2F4ED` | Muted surface |
| `--color-bark` | `#422B1C` | Body text |
| `--color-bark-light` | `#725C4E` | Muted text |
| `--color-ink` | `#000000` | Black ground |
| `--color-white` | `#FFFFFF` | Surface |

### Semantic aliases

Screens use these, not the palette directly, so intent survives a palette change:

```
--color-background          → cream-warm
--color-foreground          → bark
--color-muted-foreground    → bark-light
--color-surface             → white
--color-surface-muted       → cream-cool
--color-primary             → forest-green
--color-primary-foreground  → cream-warm
--color-accent              → olive-green
--color-border              → sage-green
--color-error               → clay-red
```

A screen that names `forest-green` instead of `primary` is a screen that has to be found and edited
when the primary changes. Unit tests assert both the palette values and the alias mapping, reading
the stylesheet as source text.

## 3. Typography

| Token | Family | Use |
| --- | --- | --- |
| `--font-sans` | DM Sans | Body |
| `--font-display` | Playfair Display | Headings |

Both are loaded through `next/font`, which downloads and self-hosts them at build time, so member
browsers never contact Google's font hosts. That is a privacy property, not a performance one.

`h1` through `h6` carry the display face by default. Tracking is tightened (`--tracking-display`,
`-0.02em`) only on `h1`–`h3`, from the point where the deck tightens it, so small headings keep their
default spacing. `--tracking-label` (`0.12em`) is for small uppercase labels.

Every font stack ends in a generic family the browser always has, and a test asserts it — including
through `var()` indirection, since `next/font`'s own value stops at its metric-matched fallback.

## 4. What the brand still owes

Two tokens are placeholders and are marked as such in the stylesheet.

### 4.1 No error colour

The deck supplies none, and the age gate needs one. `--color-clay-red` (`#8E2F2A`) is a muted brick
red picked to sit with Bark rather than a stock alarm red.

It meets AA and AAA on all three light grounds. **It is not verified on either green**, so it is for
light grounds only.

Screens reach it through `--color-error` and never name `clay-red` directly, which makes replacing it
a one-hex change when the brand supplies the real value.

### 4.2 No dark palette

There is no dark palette at all, so the dark variant is scoped to an **opt-in `.dark` class** rather
than the operating system preference:

```css
@custom-variant dark (&:where(.dark, .dark *));
```

Without that redefinition, any `dark:` utility anywhere in the product would fire from
`prefers-color-scheme` and render an unreviewed colour scheme to any member whose device is set to
dark — which is most of them.

### 4.3 Playfair Display has no Light cut

The guidelines show a "Light" weight. Playfair Display starts at 400 on Google Fonts. The loaded
weights are 400, 500, 600 and 700, and the deck's lightest specimen cannot be matched exactly.

## 5. Logo artwork

Four variants, each declaring its own dimensions and the ground it is drawn for. Components
reference these rather than hardcoding paths, so the artwork can be replaced in one place.

| Variant | File | Ground |
| --- | --- | --- |
| `onCream` | `logo-badge-cream.png` | Cream, default |
| `onForestGreen` | `logo-badge-on-green.png` | Primary green |
| `onBlack` | `logo-badge-on-black.png` | Black |
| `mark` | `logo-mark-cc.png` | Transparent. Source of the site icons. |

A test asserts the declared dimensions match the files on disk, reading width and height out of each
PNG's IHDR chunk so no image library is needed.

## 6. Photography

Four photographs from the deck's imagery-style slide. Each declares `maxRenderedWidth` — the largest
CSS width it may be rendered at, set so the file is never drawn below 2x:

| Key | Intrinsic | Max rendered |
| --- | --- | --- |
| `leafCanopy` | 1076 × 717 | 520 |
| `fieldSunrise` | 734 × 543 | 160 |
| `glovedHarvest` | 358 × 298 | 160 |
| `handsSeedling` | 288 × 278 | 140 |

The ceiling travels with the asset, a unit test asserts it is never more than half the intrinsic
width, and `Brand/BrandImage` refuses a wider request at the call site. Three mechanisms for one
constraint, because the failure this prevents happens months later and to someone who did not read
this document.

## 7. Value icons

The four brand value icons are held as **SVG path data in `lib/brand-icons.ts`**, not as files under
`public/`.

Three reasons: each icon takes its colour from `currentColor`, costs no extra request, and can be
hidden from assistive technology by the component that draws it. The deck's hardcoded white and
black fills are dropped on extraction. Each entry records what the artwork depicts — documentation,
not alternative text, since the icons are decorative and are hidden from screen readers.

## 8. Shape

| Token | Value | Use |
| --- | --- | --- |
| `--radius-card` | `1rem` | Generously rounded cards |
| `--radius-control` | `0.75rem` | Inputs and buttons |
| `--radius-pill` | `9999px` | Fully rounded pills |

Taken from the app mockup in the deck.

## 9. How this is tested

`app/globals.test.ts` reads `globals.css` as **source text** rather than through the DOM, because
jsdom does not run Tailwind and an `@theme` block is never resolved into computed styles at test
time.

The test strips comments first, so a token mentioned only in prose cannot satisfy an assertion. It
resolves `var()` references against the tokens the stylesheet itself declares, so a font stack can be
checked for a generic family even when the generic sits behind an indirection.

This is a contract test: it asserts the stylesheet matches the design recorded here. If a value in
this document changes, that test changes with it.

## 10. Risks

| # | Risk | Status |
| --- | --- | --- |
| 1 | `--color-clay-red` is not from the brand and is unverified on green grounds. Any error state on a green surface is unaccounted for. | Open — needs a brand decision |
| 2 | No dark palette. The opt-in variant prevents an unreviewed scheme from shipping, but it also means the product has no dark mode. | Open — needs a brand decision |
| 3 | Playfair Display has no Light cut on Google Fonts. The deck's lightest specimen cannot be matched. | Accepted |
| 4 | The deck's photographs are small and their render ceilings are correspondingly tight — `handsSeedling` may not exceed 140px. Any new layout wanting a large photograph needs new artwork, not a larger ceiling. | Accepted |
| 5 | Brand values are duplicated between `globals.css` and `app/globals.test.ts`, by design. The test is the contract, so both must be edited together. | Accepted |

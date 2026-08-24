# Landing page

The public face of the club, and the only route in the product a search engine may index.

## 1. Executive summary

The landing page is complete. It is one server-rendered route composed of six sections, with every
word held in one content module and held to a set of compliance patterns by automated tests.

Two things about it are worth a decision-maker's attention.

**The copy is governed, not just written.** `lib/copy-compliance.ts` holds four patterns describing
what member-facing copy may not say — no clinical claim, no retail voice, no currency, no
eligibility claim — and the tests assert the page's entire copy corpus against them. In a cannabis
product, a therapeutic claim is a regulatory exposure, and a page that reads as a shop rather than a
club is a licensing exposure. Those constraints are enforced by the build rather than by a reviewer
remembering.

**The page tells the truth about the club not being open.** The join band carries the line *"The club
is not yet open. Sign-up will follow shortly."* rather than presenting a button that leads somewhere
incomplete.

## 2. Structure

Six sections in a fixed order, asserted by test:

| Section | Component | Content |
| --- | --- | --- |
| Hero | `Landing/LandingHero` | Name, tagline, proposition, Sign Up and Log In |
| Strapline ribbon | `Landing/StraplineRibbon` | Three segments from the guidelines deck |
| Values | `Landing/BrandValues` | Four values, each with an icon |
| Story | `Landing/BrandStory` | The emblem's meaning, then three steps |
| Join band | `Landing/JoinBand` | The call to action, repeated, and the not-yet-open note |
| Footer | `Landing/LandingFooter` | Rights line, no year |

**Sign Up leads, before anything else on the page.** The first two links in document order are Sign
Up then Log In, and a test asserts exactly that.

Both actions appear twice — once in the hero, once in the join band a reader reaches by scrolling — so
a reader who scrolls does not have to scroll back.

Both Sign Up buttons point at `/join`, not `/signup`. Leaving this page for the sign-up flow is a
decision to begin, so it always starts at the age gate with any previous answer discarded. See
`sign-up.md` section 2.

The footer sits **outside** `main`. Nested inside it, a `footer` element is not exposed as the page's
`contentinfo` landmark.

The rights line carries no year, so nothing in a statically generated page goes stale.

## 3. Copy governance

Every word lives in `lib/landing-content.ts`, including `ALL_COPY` — a flattened list of every line.
That list is assembled in the content module rather than in the test, so a string cannot be added to
the page without the compliance tests seeing it. A separate test asserts that every line in
`ALL_COPY` actually appears in the rendered page, which is what ties the corpus to the markup.

The copy is fixed brand content rather than anything a caller varies, so the sections read it from
the module rather than taking it as props. That also gives the client's sign-off pass one file to
review.

### The four compliance patterns

| Pattern | Forbids | Reason |
| --- | --- | --- |
| `CLINICAL_CLAIM` | Medical, therapeutic and dosage language, including `thc`, `cbd`, `mg`, `wellness` | Cannabis copy attracts these and none is defensible |
| `RETAIL_VOICE` | `price`, `buy`, `cart`, `checkout`, `order`, `delivery`, `stock` | A club, not a shop |
| `CURRENCY` | Any amount in any notation | No amounts anywhere in the public product |
| `ELIGIBILITY_CLAIM` | `over 18`, `18+`, `adults only`, `eligible`, `licence` | Legal has not written this |

These patterns started inside the landing page's own copy test. They moved to a module of their own
when the age gate became the second surface with a corpus — two copies would have drifted, and the
rules are a product constraint rather than a property of one screen.

**Two exemptions exist, both narrow, both stated where they are taken.**

The age check is exempt from `ELIGIBILITY_CLAIM`, being the only surface that says anything about who
may join. A payment screen, if one is built, would be exempt from `CURRENCY` and `RETAIL_VOICE`
because it has to name an amount and ask to be paid.

Nothing is exempt from `CLINICAL_CLAIM`. A third exemption is the point at which these rules stop
meaning anything.

## 4. Accessibility and motion

Asserted by test rather than by review:

- **Exactly one `h1`**, and it names the club.
- **Heading levels descend without skipping one.**
- **Each section is a named landmark**, so a reader can jump between them, alongside `main` and
  `contentinfo`.
- **Nothing moves on its own.** The test asserts the rendered markup contains no `animate-`,
  `animation:` or `marquee`, so there is nothing a reader has to pause. WCAG 2.2.2.

Two content rules are also tested:

- **No photograph of an identifiable person.** The guidelines deck includes a photograph of a
  cultivator's face; publishing an identifiable person needs their consent and the deck records
  none.
- **No starter-template content.** No `page.tsx` boilerplate, no Vercel or Next.js links, and the
  five starter SVGs are gone from `public/`. A test walks `app/`, `components/` and `lib/` to
  confirm nothing still references them.

## 5. Indexing

The landing page is the only route the product ever permits to be indexed, and no environment other
than Production permits any indexing at all. See `frontend.md` section 7 for the three independent
mechanisms enforcing that.

`robots.txt` in Production pairs `Allow: /$` with `Disallow: /`, which permits the home page and
nothing below it. The `$` anchor is an extension to the original exclusion standard rather than part
of it — honoured by Google and Bing, not guaranteed elsewhere — which is exactly why the root layout
also declares `noindex` for every route by default.

Crawlable asset paths are allowed alongside it (`/_next/static/`, the icons, the favicon). A crawler
blocked from a page's stylesheet cannot assess how that page renders, and the landing page is the one
page meant to be assessed.

## 6. What is not built

There is no other public page. No about, no contact, no news, no member directory.

There is no payment or membership-status surface. Copy for one would need the `CURRENCY` and
`RETAIL_VOICE` exemptions noted in section 3, and neither the screen nor the backend behind it
exists.

## 7. Risks

| # | Risk | Status |
| --- | --- | --- |
| 1 | The landing page offers Sign Up, which leads to a form that stores nothing. The page's own note softens this, but a visitor who completes sign-up has not joined anything. | Open — see `sign-up.md` risk 1 |
| 2 | The compliance patterns are broad by design and will refuse legitimate copy. `market` blocks "marketing", `health` blocks "healthy soil". The intended remedy is rewording, not widening the pattern. | Accepted |
| 3 | `Log In` leads to a placeholder. See `authentication.md` section 8. | Open |

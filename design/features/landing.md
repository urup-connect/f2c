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

**The page now describes the members area in the present tense.** The join band's line *"The club is
not yet open. Sign-up will follow shortly."* has been removed on the client's instruction, so the
page presents cultivation offers, my plants, swap zone and subscriptions as live. Nothing behind
those names is built. This is the page's largest open exposure and is carried as risk 1.

**The club film is the first thing in the product to read `CDN_BASE_URL`.** It is a 7 MB, 61-second
1920x1080 file on the static content host, and it does not play on its own.

## 2. Structure

Six sections in a fixed order, asserted by test:

| Section | Component | Content |
| --- | --- | --- |
| Hero | `Landing/LandingHero` | Name, tagline, proposition, Sign Up and Log In |
| Strapline ribbon | `Landing/StraplineRibbon` | Three segments from the guidelines deck |
| Film | `Landing/ClubFilm` | The club film, from the CDN |
| Why join | `Landing/WhyJoin` | What the collective is, then five benefits of membership |
| Values | `Landing/BrandValues` | Four values, each with an icon |
| Story | `Landing/BrandStory` | The emblem's meaning, then three steps |
| Legal compliance | `Landing/LegalNotice` | Four points on the ground the club operates on |
| Join band | `Landing/JoinBand` | The call to action, repeated |
| Footer | `Landing/LandingFooter` | Rights line, no year |

Nine sections, alternating grounds so no two adjacent sections share one. Why join and its benefits
are **one** section rather than two: the benefits only mean anything after the paragraph that says
what the collective is, and a reader jumping between landmarks is better served by one destination
than by two that only make sense together.

Legal compliance sits **before** the closing call to action, so a reader has the ground rules before
they decide rather than after.

**Sign Up leads, before anything else on the page.** The first two links in document order are Sign
Up then Log In, and a test asserts exactly that. The film adds no link, which is what keeps this
true with a section between the hero and the rest of the page.

Both actions appear twice — once in the hero, once in the join band a reader reaches by scrolling — so
a reader who scrolls does not have to scroll back.

Both Sign Up buttons point at `/join`, not `/signup`. Leaving this page for the sign-up flow is a
decision to begin, so it always starts at the age gate with any previous answer discarded. See
`sign-up.md` section 2.

The footer sits **outside** `main`. Nested inside it, a `footer` element is not exposed as the page's
`contentinfo` landmark.

The rights line carries no year, so nothing in a statically generated page goes stale.

## 3. The club film

`Landing/ClubFilm` draws a single `video` element. Everything about the file is declared in
`lib/brand-film.ts`: path, intrinsic dimensions and duration.

**The address is built from `CDN_BASE_URL`, never hardcoded.** `brandFilmSource(config)` is pure and
takes a `SiteConfig`, exactly as `lib/seo.ts` does — the component supplies the running
application's config. A hardcoded address would mean QA serving Production's file. This is the only
reader of `cdnBaseUrl` in the application, and `lib/site.ts` records that.

| Attribute | Value | Why |
| --- | --- | --- |
| `controls` | present | The reader decides when it plays |
| `autoplay` / `loop` | **absent** | See below |
| `poster` | `…/26-f2c.webp` | The still frame, from the same CDN |
| `preload` | `metadata` | Fetches the header, not 7 MB |
| `playsInline` | present | Stays in the page on a phone |
| `width` / `height` | 1920 x 1080 | From the manifest |

**Nothing plays on its own.** The film runs 61 seconds and carries a soundtrack. Anything that
started by itself would need a pause control to satisfy WCAG 2.2.2 — the same reasoning that keeps
the strapline ribbon static rather than a marquee. Not starting is simpler and serves everyone. A
test asserts the absence of `autoplay` and `loop`.

**`preload="metadata"` is a cost decision as much as a performance one.** At 7 MB the file is most
of the page's weight, spent on something most readers never play, and this is a South African
audience on metered mobile data more often than not.

The file is laid out for streaming, which is what makes the header cheap: its `moov` atom is 68 KB
at offset 40, ahead of the media rather than behind it, so the browser gets the duration in one
range request instead of reaching past 7 MB to find it. The reader sees how long the film runs
before deciding to spend the rest.

**The poster fills the box until then.** 1201x675, 34 KB, WebP, on the same host under
`/media/26-f2c.webp`. It is declared in the manifest as its own path rather than
derived from the film's — the two are different file types on a host neither this application nor
Django controls, and deriving it would turn a renamed asset into a silently broken image. Its ratio
is 16:9 to within a pixel of the film's, asserted by test, so the box letterboxes imperceptibly
rather than cropping. The ink ground behind it covers both that edge and the moment before it
loads.

A poster needs no cross-origin handling: the browser treats it as an ordinary image. A caption
track does, which is the difference between the two assets below.

**The box is reserved from the manifest's dimensions** as a 16:9 `aspect-ratio`, so the page does not
reflow when the metadata arrives. The ratio rather than a height, because the file is fixed and the
box is fluid.

**The film is labelled by the section heading**, through `aria-labelledby`, rather than carrying an
`aria-label` of its own. An `aria-label` would be member-facing copy that the compliance corpus
could not see, because `ALL_COPY` is asserted against rendered *text*. Pointing at the visible
heading keeps the announced name inside the governed corpus.

### Captions are not wired in

A `.vtt` file now sits beside the film, and the page does **not** reference it. A test asserts the
absence of a `track` element, so this is a deliberate state rather than an oversight.

Three things block it, and all three are on the host or in the asset rather than in this code:

1. **The file is a placeholder.** Its own `NOTE` block says so — *"Template only — timestamps and
   text below are placeholders"* — and its three cues cover the first ten seconds of a 62-second
   film with bracketed stand-in text. Wiring it up would put
   `[Caption text for the first line of dialogue/narration]` over the film for any reader with
   captions switched on.
2. **It is served as `text/plain`, not `text/vtt`.** Browsers reject a `track` whose source arrives
   under the wrong type, so it would not load even if the content were right.
3. **The host sends no `Access-Control-Allow-Origin`.** A cross-origin text track is always fetched
   in CORS mode, so the track needs the header and the `video` element needs a `crossorigin`
   attribute. Adding `crossorigin` also puts the film itself under CORS, so the header has to cover
   the `.mp4` as well or the film stops playing.

The order matters: fixing 2 and 3 without fixing 1 publishes placeholder text on the one page the
product permits to be indexed. See risk 4.

## 4. Copy governance

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

### The client copy, and what was changed to admit it

The *Why join*, *Benefits* and *Legal compliance* copy was supplied by the client and tripped two of
the four patterns. **The remedy was rewording, never a widened pattern** — risk 2 below states why,
and the decision was taken explicitly rather than by default.

| Supplied | Published | Pattern |
| --- | --- | --- |
| "receive harvest via private delivery" | "receive your harvest by private collection" | `RETAIL_VOICE` |
| "Exclusive discounts on monthly supply subscriptions" | "Preferential member terms on monthly supply subscriptions" | `RETAIL_VOICE` |
| "Adults only (18+)" | "Every applicant completes an age check before sign-up begins" | `ELIGIBILITY_CLAIM` |

The third is the substantive one. The supplied line states a threshold; the published line states
the check the product actually performs. The age gate remains the only surface exempt from
`ELIGIBILITY_CLAIM`, and a second exemption would empty the rule out.

The supplied copy also named the club **"F2C Cannabis Club"**. The product is Cultivators Collective
throughout — hero, footer, metadata and logo alt text, all test-asserted — and the film's own
filename is `26-f2c.mp4`, so the name was treated as a paste from a sibling brand
and corrected. A test asserts the published body names Cultivators Collective and not F2C.

**Two exemptions exist, both narrow, both stated where they are taken.**

The age check is exempt from `ELIGIBILITY_CLAIM`, being the only surface that says anything about who
may join. A payment screen, if one is built, would be exempt from `CURRENCY` and `RETAIL_VOICE`
because it has to name an amount and ask to be paid.

Nothing is exempt from `CLINICAL_CLAIM`. A third exemption is the point at which these rules stop
meaning anything.

## 5. Accessibility and motion

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

The film is held to the same motion rule: it carries neither `autoplay` nor `loop`, asserted by
test. It is **not** captioned — see risk 4.

## 6. Indexing

The landing page is the only route the product ever permits to be indexed, and no environment other
than Production permits any indexing at all. See `frontend.md` section 7 for the three independent
mechanisms enforcing that.

**The host is `f2c-cannabis.co.za`** — this application is the club's whole front door, landing page
and member zone together, and `f2c.co.za` is the produce store rather than a marketing site in front
of it. See `conflict.md` C30. Everything indexed here is built from this deployment's own
`SITE_URL`, so the rules are per host without needing to be told which host.

`robots.txt` in Production pairs `Allow: /$` with `Disallow: /`, which permits the home page and
nothing below it. The `$` anchor is an extension to the original exclusion standard rather than part
of it — honoured by Google and Bing, not guaranteed elsewhere — which is exactly why the root layout
also declares `noindex` for every route by default.

Crawlable asset paths are allowed alongside it (`/_next/static/`, the icons, the favicon). A crawler
blocked from a page's stylesheet cannot assess how that page renders, and the landing page is the one
page meant to be assessed.

## 7. What is not built

There is no other public page. No about, no contact, no news, no member directory, and no terms or
privacy page for the legal compliance section to link to.

There is no payment or membership-status surface. Copy for one would need the `CURRENCY` and
`RETAIL_VOICE` exemptions noted in section 3, and neither the screen nor the backend behind it
exists.

## 8. Risks

| # | Risk | Status |
| --- | --- | --- |
| 1 | **The page describes an unbuilt members area in the present tense.** Cultivation offers, my plants, swap zone and subscriptions are named as things membership gives a member; none exists, and Sign Up still leads to a form that stores nothing. The softening note was removed on the client's instruction. A visitor who signs up today finds nothing there. | **Open — client decision, taken 2026-08-25** |
| 2 | The compliance patterns are broad by design and will refuse legitimate copy. `market` blocks "marketing", `health` blocks "healthy soil". The intended remedy is rewording, not widening the pattern. | Accepted — exercised in section 4 |
| 3 | The film had no poster frame. | **Closed** — `26-f2c.webp` supplied and wired in |
| 4 | **The film carries a soundtrack and no captions.** WCAG 1.2.2 (Captions, Prerecorded) is Level A, so this is a conformance failure on the one page the product permits to be indexed. A `.vtt` exists on the CDN but is a placeholder template, is served as `text/plain` rather than `text/vtt`, and the host sends no CORS header — all three must be fixed, and the content first. See section 3. | Open — real captions and two host settings needed |
| 5 | The legal compliance section is a summary, not the club's terms, and there is no terms page to link it to. The four points paraphrase the Constitutional Court ruling and the Cannabis for Private Purposes Act; the wording has not been through an attorney. | Open — legal review needed |
| 6 | `Log In` leads to a placeholder. See `authentication.md` section 8. | Open |
| 7 | **`/` is statically prerendered, so the film's CDN address is fixed at build time.** A build artefact produced in QA and promoted to Production would serve the film from the QA host. Same class as `frontend.md` risk 2, and the root layout's `metadataBase` is already fixed the same way on this route. The remedy is to build per environment, not to make the one indexable page dynamic. | Open — see `frontend.md` risk 7 |

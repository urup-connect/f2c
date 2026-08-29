import { LANDING } from '@/lib/landing-content'

/**
 * Says, high on the front door, that the store is not trading yet.
 *
 * **This is a content decision rather than a component that will be deleted.** A landing page that
 * invited a shopper to browse would send them to a catalogue that does not exist; one that said
 * nothing would leave them hunting for it. Saying so plainly, above the explanation of how it will
 * work, is what makes the rest of the page read as a description rather than as a promise.
 *
 * It is not a `role="alert"` and not an error colour. Nothing has gone wrong — a store that has not
 * opened is a fact about the store, and dressing it as a warning would suggest otherwise.
 *
 * When the catalogue lands, this comes off the page and the hero's first control changes from "create
 * an account" to "browse". That is the whole change, which is why the notice is its own component.
 */
export const NotOpenNotice = () => (
  <section className="mx-auto max-w-5xl px-6 pt-16">
    <div className="rounded-card border-2 border-dashed border-border bg-surface-muted p-6 sm:p-8">
      <h2 className="font-display text-2xl tracking-display text-leaf">
        {LANDING.notYet.heading}
      </h2>
      <p className="mt-3 max-w-2xl font-sans text-base leading-relaxed text-foreground">
        {LANDING.notYet.body}
      </p>
    </div>
  </section>
)

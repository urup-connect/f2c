import { VALUES } from '@/lib/landing-content'
import { BrandValueCard } from './BrandValueCard'

/**
 * The four brand values, quoted from the guidelines deck.
 *
 * Named as a landmark by its own heading, so a screen reader user can jump straight to it on a
 * page this long.
 * See design/features/landing-page-engagement.md criteria 10 and 21.
 */
export const BrandValues = () => (
  <section aria-labelledby="values-heading" className="bg-background">
    <div className="mx-auto flex max-w-6xl flex-col gap-10 px-6 py-20">
      <h2
        id="values-heading"
        className="max-w-2xl font-display text-3xl tracking-display text-forest-green sm:text-4xl"
      >
        {VALUES.heading}
      </h2>

      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {VALUES.items.map((item) => (
          <BrandValueCard
            key={item.label}
            iconKey={item.iconKey}
            label={item.label}
            description={item.description}
          />
        ))}
      </ul>
    </div>
  </section>
)

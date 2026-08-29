import type { MetadataRoute } from 'next'
import { robotsRules } from '@/lib/seo'
import { SITE_CONFIG } from '@/lib/site'

// Read at request time, so one build artefact behaves correctly in QA and in Production.
export const dynamic = 'force-dynamic'

export default function robots(): MetadataRoute.Robots {
  return robotsRules(SITE_CONFIG)
}

import type { MetadataRoute } from 'next'
import { patterns, guides, caseStudies } from '@/.velite'

const BASE = 'https://prajwalamte.github.io/AI-Engineering-Patterns'

export default function sitemap(): MetadataRoute.Sitemap {
  const staticRoutes: MetadataRoute.Sitemap = [
    { url: `${BASE}/`, priority: 1.0, changeFrequency: 'weekly' },
    { url: `${BASE}/patterns/`, priority: 0.9, changeFrequency: 'weekly' },
    { url: `${BASE}/guides/`, priority: 0.8, changeFrequency: 'monthly' },
    { url: `${BASE}/case-studies/`, priority: 0.7, changeFrequency: 'monthly' },
    { url: `${BASE}/graph/`, priority: 0.6, changeFrequency: 'monthly' },
  ]

  const patternRoutes: MetadataRoute.Sitemap = patterns.map((p) => ({
    url: `${BASE}/patterns/${p.slug}/`,
    priority: 0.8,
    changeFrequency: 'monthly' as const,
  }))

  const guideRoutes: MetadataRoute.Sitemap = guides.map((g) => ({
    url: `${BASE}/guides/${g.slug}/`,
    priority: 0.7,
    changeFrequency: 'monthly' as const,
  }))

  const caseStudyRoutes: MetadataRoute.Sitemap = caseStudies.map((cs) => ({
    url: `${BASE}/case-studies/${cs.slug}/`,
    priority: 0.7,
    changeFrequency: 'monthly' as const,
  }))

  return [...staticRoutes, ...patternRoutes, ...guideRoutes, ...caseStudyRoutes]
}

import { patterns, caseStudies, guides } from '@/.velite'

export { patterns, caseStudies, guides }

export const PILLAR_ORDER = [
  'inference-and-serving',
  'retrieval-and-memory',
  'data-patterns',
  'reliability',
  'observability',
  'security-and-trust',
  'cost-and-efficiency',
  'governance',
  'graph-patterns',
  'evaluation-and-testing',
] as const

export const PILLAR_LABELS: Record<string, string> = {
  'inference-and-serving': 'Inference & Serving',
  'retrieval-and-memory': 'Retrieval & Memory',
  'data-patterns': 'Data Patterns',
  'reliability': 'Reliability & Resilience',
  'observability': 'Observability',
  'security-and-trust': 'Security & Trust',
  'cost-and-efficiency': 'Cost & Efficiency',
  'governance': 'Governance',
  'graph-patterns': 'Graph Patterns',
  'evaluation-and-testing': 'Evaluation & Testing',
}

export const STATUS_LABELS: Record<string, string> = {
  'proposed': 'Proposed',
  'emerging': 'Emerging',
  'validated-in-production': 'Validated in Production',
}

export const STATUS_COLORS: Record<string, string> = {
  'proposed': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
  'emerging': 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  'validated-in-production': 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
}

export function getPatternsByPillar(pillar: string) {
  return patterns
    .filter((p) => p.pillar === pillar)
    .sort(
      (a, b) =>
        (a.sidebar?.order ?? 99) - (b.sidebar?.order ?? 99) ||
        a.title.localeCompare(b.title),
    )
}

export function getPatternBySlug(slug: string) {
  return patterns.find((p) => p.slug === slug)
}

// Resolves human-readable related pattern names (e.g. "Hybrid Search Pattern")
// to actual pattern objects by fuzzy-matching against titles.
export function resolveRelated(names: string[]) {
  return names.map((name) => {
    const needle = name
      .toLowerCase()
      .replace(/\s+pattern$/i, '')
      .replace(/[^a-z0-9\s]/g, '')
      .trim()

    const found = patterns.find((p) => {
      const haystack = p.title.toLowerCase().replace(/[^a-z0-9\s]/g, '')
      return haystack === needle || haystack.includes(needle) || needle.includes(haystack)
    })

    return { name, pattern: found ?? null }
  })
}

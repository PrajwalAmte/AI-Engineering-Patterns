import { patterns, caseStudies, guides } from '@/.velite'

export { patterns, caseStudies, guides }

export const PILLAR_ORDER = [
  'inference-and-serving',
  'retrieval-and-memory',
  'data-patterns',
  'reliability',
  'observability-and-evaluation',
  'security-and-trust',
  'cost-and-efficiency',
  'governance',
  'graph-patterns',
  'loop-engineering',
] as const

export const PILLAR_LABELS: Record<string, string> = {
  'inference-and-serving': 'Inference & Serving',
  'retrieval-and-memory': 'Retrieval & Memory',
  'data-patterns': 'Data Patterns',
  'reliability': 'Reliability & Resilience',
  'observability-and-evaluation': 'Observability & Evaluation',
  'security-and-trust': 'Security & Trust',
  'cost-and-efficiency': 'Cost & Efficiency',
  'governance': 'Governance',
  'graph-patterns': 'Graph Patterns',
  'loop-engineering': 'Loop Engineering',
}

export const PILLAR_DESCRIPTIONS: Record<string, string> = {
  'inference-and-serving': 'Getting requests to the right model, cheaply and reliably.',
  'retrieval-and-memory': 'Finding the right context, and knowing when it isn’t there.',
  'data-patterns': 'Keeping the data under your index and models trustworthy.',
  'reliability': 'Staying up when providers slow down, fail, or return junk.',
  'observability-and-evaluation': 'Seeing what happened, and knowing whether quality moved.',
  'security-and-trust': 'Limiting what bad input, or a hijacked agent, can do.',
  'cost-and-efficiency': 'Spending tokens and tool calls where they matter.',
  'governance': 'Approvals, rollouts and documentation that hold up.',
  'graph-patterns': 'Relationships, entities and reasoning beyond a single chain.',
  'loop-engineering': 'Agent loops that stop, verify, learn and recover.',
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

// Must stay in sync with normalize() in scripts/validate-schema.js, which
// fails the build when a related name matches no title.
export function normalizeTitle(s: string) {
  return s
    .toLowerCase()
    .replace(/[–—]/g, '-')
    .replace(/[^a-z0-9\s-]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

// Resolves related pattern titles from frontmatter to pattern objects.
export function resolveRelated(names: string[]) {
  return names.map((name) => {
    const needle = normalizeTitle(name)
    const found = patterns.find((p) => normalizeTitle(p.title) === needle)
    return { name, pattern: found ?? null }
  })
}

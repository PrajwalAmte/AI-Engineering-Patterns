import Link from 'next/link'
import { patterns } from '@/.velite'
import { PillarFilter } from '@/components/patterns/PillarFilter'

export const metadata = {
  title: 'All patterns',
  description: 'Every pattern for production LLM systems, grouped by pillar, each with a runnable, tested reference implementation.',
}

export default function PatternsPage() {
  const items = patterns.map((p) => ({
    title: p.title,
    slug: p.slug,
    pillar: p.pillar,
    status: p.status,
    description: p.description,
    tags: p.tags,
    order: p.sidebar?.order ?? 99,
  }))
    .sort((a, b) => a.order - b.order || a.title.localeCompare(b.title))

  return (
    <main className="min-w-0 flex-1">
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-gray-900 dark:text-gray-50 mb-2">
          Patterns
        </h1>
        <p className="text-gray-500 dark:text-gray-400">
          {patterns.length} patterns across {new Set(patterns.map((p) => p.pillar)).size} pillars, each with a runnable, tested example.
          Not sure where to start? Try the <Link href="/guides/decision-guide" className="text-[var(--accent)] hover:underline">decision guide</Link>.
        </p>
      </div>
      <PillarFilter patterns={items} />
    </main>
  )
}

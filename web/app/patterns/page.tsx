import { patterns } from '@/.velite'
import { PillarFilter } from '@/components/patterns/PillarFilter'

export const metadata = {
  title: 'Patterns | AI Engineering Patterns',
  description: 'Browse all production AI engineering patterns grouped by pillar.',
}

export default function PatternsPage() {
  const items = patterns.map((p) => ({
    title: p.title,
    slug: p.slug,
    pillar: p.pillar,
    status: p.status,
    description: p.description,
    tags: p.tags,
  }))

  return (
    <main className="min-w-0 flex-1">
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-gray-900 dark:text-gray-50 mb-2">
          Patterns
        </h1>
        <p className="text-gray-500 dark:text-gray-400">
          {patterns.length} production-ready patterns across {new Set(patterns.map((p) => p.pillar)).size} pillars.
        </p>
      </div>
      <PillarFilter patterns={items} />
    </main>
  )
}

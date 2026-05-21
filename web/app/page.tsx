import Link from 'next/link'
import { patterns } from '@/.velite'
import { PILLAR_ORDER, PILLAR_LABELS } from '@/lib/patterns'

export default function Home() {
  const pillarCounts = PILLAR_ORDER.reduce<Record<string, number>>((acc, p) => {
    acc[p] = patterns.filter((pat) => pat.pillar === p).length
    return acc
  }, {})

  return (
    <main className="max-w-screen-xl mx-auto px-6">
      {/* Hero */}
      <section className="pt-24 pb-16 text-center">
        <div className="inline-flex items-center gap-2 rounded-full border border-violet-200 dark:border-violet-800 bg-violet-50 dark:bg-violet-950/40 px-3 py-1 text-xs font-medium text-violet-700 dark:text-violet-300 mb-6">
          {patterns.length} patterns · {PILLAR_ORDER.length} pillars
        </div>
        <h1 className="text-5xl font-bold tracking-tight text-gray-900 dark:text-gray-50 mb-5 max-w-3xl mx-auto leading-tight">
          AI Engineering
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-[var(--accent)] via-[var(--accent-cyan)] to-[var(--accent-violet)]">
            {' '}Patterns
          </span>
        </h1>
        <p className="text-lg text-gray-500 dark:text-gray-400 max-w-xl mx-auto mb-10 leading-relaxed">
          A living catalogue of battle-tested patterns for building production AI systems — from inference infrastructure to governance.
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          <Link
            href="/patterns"
            className="inline-flex items-center gap-2 rounded-lg bg-[var(--accent)] px-5 py-2.5 text-sm font-medium text-white hover:opacity-90 transition-opacity"
          >
            Browse Patterns
          </Link>
          <Link
            href="/guides/getting-started"
            className="inline-flex items-center gap-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-5 py-2.5 text-sm font-medium text-gray-700 dark:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600 transition-colors"
          >
            Getting Started
          </Link>
          <Link
            href="/graph"
            className="inline-flex items-center gap-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-5 py-2.5 text-sm font-medium text-gray-700 dark:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600 transition-colors"
          >
            Pattern Graph
          </Link>
        </div>
      </section>

      {/* Pillar grid */}
      <section className="py-12">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-6 text-center">
          Browse by pillar
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          {PILLAR_ORDER.map((pillar) => (
            <Link
              key={pillar}
              href={`/patterns?pillar=${pillar}`}
              className="group flex flex-col rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 hover:border-violet-300 dark:hover:border-violet-700 hover:shadow-sm transition-all"
            >
              <span className="text-2xl font-bold tabular-nums text-[var(--accent)] mb-1">
                {pillarCounts[pillar] ?? 0}
              </span>
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300 group-hover:text-[var(--accent)] transition-colors leading-snug">
                {PILLAR_LABELS[pillar]}
              </span>
            </Link>
          ))}
        </div>
      </section>
    </main>
  )
}

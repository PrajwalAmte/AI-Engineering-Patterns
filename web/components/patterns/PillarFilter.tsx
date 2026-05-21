'use client'

import { useState, useEffect } from 'react'
import { PatternCard } from './PatternCard'
import { PILLAR_ORDER, PILLAR_LABELS } from '@/lib/patterns'

interface PatternItem {
  title: string
  slug: string
  pillar: string
  status: string
  description?: string
  tags: string[]
}

interface Props {
  patterns: PatternItem[]
}

export function PillarFilter({ patterns }: Props) {
  const [active, setActive] = useState<string>('all')

  // Read ?pillar= from URL on mount to support deep-linking from homepage cards.
  useEffect(() => {
    const p = new URLSearchParams(window.location.search).get('pillar')
    if (p) setActive(p)
  }, [])

  const visible =
    active === 'all' ? patterns : patterns.filter((p) => p.pillar === active)

  return (
    <>
      <div className="flex flex-wrap gap-2 mb-8">
        <button
          onClick={() => setActive('all')}
          className={`rounded-full px-3 py-1 text-sm font-medium transition-colors ${
            active === 'all'
              ? 'bg-[var(--accent)] text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700'
          }`}
        >
          All ({patterns.length})
        </button>
        {PILLAR_ORDER.filter((p) => patterns.some((pat) => pat.pillar === p)).map((pillar) => {
          const count = patterns.filter((p) => p.pillar === pillar).length
          return (
            <button
              key={pillar}
              onClick={() => setActive(pillar)}
              className={`rounded-full px-3 py-1 text-sm font-medium transition-colors ${
                active === pillar
                  ? 'bg-[var(--accent)] text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700'
              }`}
            >
              {PILLAR_LABELS[pillar]} ({count})
            </button>
          )
        })}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {visible.map((p) => (
          <PatternCard
            key={p.slug}
            title={p.title}
            slug={p.slug}
            pillar={p.pillar}
            status={p.status}
            description={p.description}
            tags={p.tags}
          />
        ))}
      </div>
    </>
  )
}

'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { PILLAR_ORDER, PILLAR_LABELS, getPatternsByPillar } from '@/lib/patterns'

export function SidebarNav() {
  const pathname = usePathname()

  return (
    <nav className="text-sm space-y-5">
      <div>
        <Link
          href="/patterns"
          className={`block py-1 font-medium transition-colors ${
            pathname === '/patterns'
              ? 'text-[var(--accent)]'
              : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-50'
          }`}
        >
          All Patterns
        </Link>
      </div>

      {PILLAR_ORDER.map((pillar) => {
        const pillarPatterns = getPatternsByPillar(pillar)
        if (pillarPatterns.length === 0) return null

        return (
          <div key={pillar}>
            <p className="mb-1.5 px-0 text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
              {PILLAR_LABELS[pillar]}
            </p>
            <ul className="space-y-0.5">
              {pillarPatterns.map((p) => {
                const href = `/patterns/${p.slug}`
                const isActive = pathname === href
                return (
                  <li key={p.slug}>
                    <Link
                      href={href}
                      className={`block rounded px-2 py-1 transition-colors ${
                        isActive
                          ? 'bg-violet-50 text-[var(--accent)] dark:bg-violet-950/40 dark:text-violet-300 font-medium'
                          : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-gray-50'
                      }`}
                    >
                      {p.title}
                    </Link>
                  </li>
                )
              })}
            </ul>
          </div>
        )
      })}
    </nav>
  )
}

import Link from 'next/link'
import { guides } from '@/.velite'

export const metadata = {
  title: 'Guides | AI Engineering Patterns',
  description: 'Getting started guides and reference material for AI engineering patterns.',
}

export default function GuidesPage() {
  return (
    <main className="max-w-4xl mx-auto px-6 py-12">
      <div className="mb-10">
        <h1 className="text-3xl font-bold tracking-tight text-gray-900 dark:text-gray-50 mb-2">
          Guides
        </h1>
        <p className="text-gray-500 dark:text-gray-400">
          Getting started guides and reference material.
        </p>
      </div>

      <div className="space-y-3">
        {guides.map((g) => (
          <Link
            key={g.slug}
            href={`/guides/${g.slug}`}
            className="group flex items-center justify-between rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 px-5 py-4 hover:border-violet-300 dark:hover:border-violet-700 hover:shadow-sm transition-all"
          >
            <div>
              <h2 className="font-semibold text-gray-900 dark:text-gray-50 group-hover:text-[var(--accent)] transition-colors">
                {g.title}
              </h2>
              {g.description && (
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
                  {g.description}
                </p>
              )}
            </div>
            <svg
              className="w-4 h-4 text-gray-400 group-hover:text-[var(--accent)] shrink-0 ml-4 transition-colors"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
            </svg>
          </Link>
        ))}
      </div>
    </main>
  )
}

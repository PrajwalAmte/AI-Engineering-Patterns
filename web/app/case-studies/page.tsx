import Link from 'next/link'
import { caseStudies } from '@/.velite'

export const metadata = {
  title: 'Case Studies | AI Engineering Patterns',
  description: 'Real-world applications of AI engineering patterns.',
}

export default function CaseStudiesPage() {
  return (
    <main className="max-w-4xl mx-auto px-6 py-12">
      <div className="mb-10">
        <h1 className="text-3xl font-bold tracking-tight text-gray-900 dark:text-gray-50 mb-2">
          Case Studies
        </h1>
        <p className="text-gray-500 dark:text-gray-400">
          Real-world applications of AI engineering patterns in production.
        </p>
      </div>

      <div className="space-y-4">
        {caseStudies.map((cs) => (
          <Link
            key={cs.slug}
            href={`/case-studies/${cs.slug}`}
            className="group block rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-6 hover:border-violet-300 dark:hover:border-violet-700 hover:shadow-sm transition-all"
          >
            {cs.subject && (
              <p className="text-xs font-medium text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-1">
                {cs.subject}
              </p>
            )}
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-50 group-hover:text-[var(--accent)] transition-colors mb-1">
              {cs.title}
            </h2>
            {cs.description && (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {cs.description}
              </p>
            )}
            {cs.patterns && cs.patterns.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-3">
                {cs.patterns.map((p) => (
                  <span
                    key={p}
                    className="inline-flex items-center rounded px-2 py-0.5 text-xs bg-violet-50 text-violet-700 dark:bg-violet-950/40 dark:text-violet-300"
                  >
                    {p}
                  </span>
                ))}
              </div>
            )}
          </Link>
        ))}
      </div>
    </main>
  )
}

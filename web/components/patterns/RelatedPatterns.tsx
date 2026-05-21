import Link from 'next/link'
import { resolveRelated } from '@/lib/patterns'

interface Props {
  related: string[]
}

export function RelatedPatterns({ related }: Props) {
  if (related.length === 0) return null

  const resolved = resolveRelated(related)

  return (
    <aside className="mt-16 pt-8 border-t border-gray-200 dark:border-gray-800">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-4">
        Related Patterns
      </h2>
      <ul className="flex flex-wrap gap-2">
        {resolved.map(({ name, pattern }) =>
          pattern ? (
            <li key={name}>
              <Link
                href={`/patterns/${pattern.slug}`}
                className="inline-block rounded-full border border-violet-200 dark:border-violet-800 bg-violet-50 dark:bg-violet-950/30 px-3 py-1 text-sm text-violet-700 dark:text-violet-300 hover:border-violet-400 dark:hover:border-violet-600 transition-colors"
              >
                {pattern.title}
              </Link>
            </li>
          ) : (
            <li key={name}>
              <span className="inline-block rounded-full border border-gray-200 dark:border-gray-700 px-3 py-1 text-sm text-gray-500 dark:text-gray-400">
                {name}
              </span>
            </li>
          ),
        )}
      </ul>
    </aside>
  )
}

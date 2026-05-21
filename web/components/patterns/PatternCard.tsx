import Link from 'next/link'
import { STATUS_LABELS, STATUS_COLORS, PILLAR_LABELS } from '@/lib/patterns'

interface Props {
  title: string
  slug: string
  pillar: string
  status: string
  description?: string
  tags: string[]
}

export function PatternCard({ title, slug, pillar, status, description, tags }: Props) {
  return (
    <Link
      href={`/patterns/${slug}`}
      className="group block rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5 hover:border-violet-300 dark:hover:border-violet-700 hover:shadow-sm transition-all"
    >
      <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
        <span className="text-xs text-gray-400 dark:text-gray-500 uppercase tracking-wider">
          {PILLAR_LABELS[pillar] ?? pillar}
        </span>
        <span
          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[status] ?? ''}`}
        >
          {STATUS_LABELS[status] ?? status}
        </span>
      </div>

      <h3 className="font-semibold text-gray-900 dark:text-gray-50 group-hover:text-[var(--accent)] transition-colors mb-1.5">
        {title}
      </h3>

      {description && (
        <p className="text-sm text-gray-500 dark:text-gray-400 line-clamp-2 leading-relaxed">
          {description}
        </p>
      )}

      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-3">
          {tags.slice(0, 4).map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center rounded px-1.5 py-0.5 text-xs bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400"
            >
              {tag}
            </span>
          ))}
        </div>
      )}
    </Link>
  )
}

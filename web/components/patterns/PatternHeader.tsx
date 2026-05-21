import { STATUS_LABELS, STATUS_COLORS, PILLAR_LABELS } from '@/lib/patterns'

interface Props {
  title: string
  pillar: string
  status: string
  description?: string
  tags: string[]
  lastUpdated?: string
  contributors?: string[]
}

export function PatternHeader({
  title,
  pillar,
  status,
  description,
  tags,
  lastUpdated,
  contributors,
}: Props) {
  return (
    <div className="mb-10 pb-8 border-b border-gray-200 dark:border-gray-800">
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
          {PILLAR_LABELS[pillar] ?? pillar}
        </span>
        <span aria-hidden className="text-gray-300 dark:text-gray-600">·</span>
        <span
          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_COLORS[status] ?? ''}`}
        >
          {STATUS_LABELS[status] ?? status}
        </span>
      </div>

      <h1 className="text-3xl font-bold tracking-tight text-gray-900 dark:text-gray-50 mb-3">
        {title}
      </h1>

      {description && (
        <p className="text-lg leading-relaxed text-gray-600 dark:text-gray-300 mb-4">
          {description}
        </p>
      )}

      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {tags.map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center rounded px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      {(lastUpdated || contributors?.length) && (
        <div className="flex gap-3 mt-4 text-xs text-gray-400 dark:text-gray-500">
          {lastUpdated && <span>Updated {lastUpdated}</span>}
          {contributors?.map((c) => (
            <span key={c}>{c}</span>
          ))}
        </div>
      )}
    </div>
  )
}

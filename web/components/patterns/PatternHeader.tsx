import Link from 'next/link'
import { STATUS_LABELS, STATUS_COLORS, PILLAR_LABELS } from '@/lib/patterns'
import { exampleUrls } from '@/lib/site'
import { CopyCommand } from './CopyCommand'

interface Props {
  title: string
  pillar: string
  status: string
  description?: string
  tags: string[]
  lastUpdated?: string
  example?: string
}

export function PatternHeader({ title, pillar, status, description, tags, lastUpdated, example }: Props) {
  const urls = example ? exampleUrls(example) : null

  return (
    <div className="mb-10 pb-8 border-b border-gray-200 dark:border-gray-800">
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <Link
          href={`/patterns?pillar=${pillar}`}
          className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider hover:text-[var(--accent)]"
        >
          {PILLAR_LABELS[pillar] ?? pillar}
        </Link>
        <span aria-hidden className="text-gray-300 dark:text-gray-600">·</span>
        <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_COLORS[status] ?? ''}`}>
          {STATUS_LABELS[status] ?? status}
        </span>
        {lastUpdated && (
          <>
            <span aria-hidden className="text-gray-300 dark:text-gray-600">·</span>
            <span className="text-xs text-gray-400 dark:text-gray-500">Updated {lastUpdated}</span>
          </>
        )}
      </div>

      <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-gray-900 dark:text-gray-50 mb-3">{title}</h1>

      {description && <p className="text-lg leading-relaxed text-gray-600 dark:text-gray-300 mb-5">{description}</p>}

      {urls && (
        <div className="rounded-lg border border-emerald-200 dark:border-emerald-900/70 bg-emerald-50/70 dark:bg-emerald-950/30 p-4 mb-5">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mb-3">
            <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-emerald-800 dark:text-emerald-300">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden>
                <path d="M20 6 9 17l-5-5" />
              </svg>
              Runnable example, tested in CI
            </span>
            <a href={urls.code} target="_blank" rel="noopener noreferrer" className="text-sm text-emerald-700 dark:text-emerald-400 hover:underline">
              Source
            </a>
            <a href={urls.test} target="_blank" rel="noopener noreferrer" className="text-sm text-emerald-700 dark:text-emerald-400 hover:underline">
              Tests
            </a>
            <a href="#implementation-example" className="text-sm text-emerald-700 dark:text-emerald-400 hover:underline">
              Jump to code
            </a>
          </div>
          <CopyCommand command={urls.command} />
        </div>
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
    </div>
  )
}

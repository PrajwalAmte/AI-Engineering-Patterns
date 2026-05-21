import { notFound } from 'next/navigation'
import { caseStudies } from '@/.velite'
import type { Metadata } from 'next'
import { ArticleBody } from '@/components/patterns/ArticleBody'
import { TableOfContents } from '@/components/layout/TableOfContents'

interface Props {
  params: Promise<{ slug: string }>
}

export async function generateStaticParams() {
  return caseStudies.map((cs) => ({ slug: cs.slug }))
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params
  const cs = caseStudies.find((c) => c.slug === slug)
  if (!cs) return {}
  return {
    title: cs.title,
    description: cs.description,
  }
}

export default async function CaseStudyPage({ params }: Props) {
  const { slug } = await params
  const cs = caseStudies.find((c) => c.slug === slug)
  if (!cs) notFound()

  return (
    <div className="max-w-screen-xl mx-auto px-6 py-12 flex gap-12">
      <main className="min-w-0 flex-1 max-w-3xl">
        <div className="mb-10 pb-8 border-b border-gray-200 dark:border-gray-800">
          {cs.subject && (
            <p className="text-xs font-medium text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-2">
              {cs.subject}
            </p>
          )}
          <h1 className="text-3xl font-bold tracking-tight text-gray-900 dark:text-gray-50 mb-3">
            {cs.title}
          </h1>
          {cs.description && (
            <p className="text-lg leading-relaxed text-gray-600 dark:text-gray-300">
              {cs.description}
            </p>
          )}
          {cs.patterns && cs.patterns.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-4">
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
          {cs.last_updated && (
            <p className="mt-4 text-xs text-gray-400 dark:text-gray-500">
              Updated {cs.last_updated}
            </p>
          )}
        </div>
        <ArticleBody html={cs.body} />
      </main>
      <TableOfContents toc={cs.toc} />
    </div>
  )
}

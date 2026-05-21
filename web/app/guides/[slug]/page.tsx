import { notFound } from 'next/navigation'
import { guides } from '@/.velite'
import type { Metadata } from 'next'
import { ArticleBody } from '@/components/patterns/ArticleBody'
import { TableOfContents } from '@/components/layout/TableOfContents'

interface Props {
  params: Promise<{ slug: string }>
}

export async function generateStaticParams() {
  return guides.map((g) => ({ slug: g.slug }))
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params
  const guide = guides.find((g) => g.slug === slug)
  if (!guide) return {}
  return {
    title: guide.title,
    description: guide.description,
  }
}

export default async function GuidePage({ params }: Props) {
  const { slug } = await params
  const guide = guides.find((g) => g.slug === slug)
  if (!guide) notFound()

  return (
    <div className="max-w-screen-xl mx-auto px-6 py-12 flex gap-12">
      <main className="min-w-0 flex-1 max-w-3xl">
        <div className="mb-10 pb-8 border-b border-gray-200 dark:border-gray-800">
          <h1 className="text-3xl font-bold tracking-tight text-gray-900 dark:text-gray-50 mb-3">
            {guide.title}
          </h1>
          {guide.description && (
            <p className="text-lg leading-relaxed text-gray-600 dark:text-gray-300">
              {guide.description}
            </p>
          )}
        </div>
        <ArticleBody html={guide.body} />
      </main>
      <TableOfContents toc={guide.toc} />
    </div>
  )
}

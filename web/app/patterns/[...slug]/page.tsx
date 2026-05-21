import { notFound } from 'next/navigation'
import { patterns } from '@/.velite'
import type { Metadata } from 'next'
import { PatternHeader } from '@/components/patterns/PatternHeader'
import { ArticleBody } from '@/components/patterns/ArticleBody'
import { RelatedPatterns } from '@/components/patterns/RelatedPatterns'
import { TableOfContents } from '@/components/layout/TableOfContents'

interface Props {
  params: Promise<{ slug: string[] }>
}

export async function generateStaticParams() {
  return patterns.map((p) => ({
    slug: p.slug.split('/'),
  }))
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params
  const pattern = patterns.find((p) => p.slug === slug.join('/'))
  if (!pattern) return {}
  return {
    title: pattern.title,
    description: pattern.description,
  }
}

export default async function PatternPage({ params }: Props) {
  const { slug } = await params
  const pattern = patterns.find((p) => p.slug === slug.join('/'))

  if (!pattern) notFound()

  return (
    <>
      <main className="min-w-0 flex-1">
        <PatternHeader
          title={pattern.title}
          pillar={pattern.pillar}
          status={pattern.status}
          description={pattern.description}
          tags={pattern.tags}
          lastUpdated={pattern.last_updated}
          contributors={pattern.contributors}
        />
        <ArticleBody html={pattern.body} />
        {pattern.related && pattern.related.length > 0 && (
          <RelatedPatterns related={pattern.related} />
        )}
      </main>

      <TableOfContents toc={pattern.toc} />
    </>
  )
}

import Link from 'next/link'
import { notFound } from 'next/navigation'
import { patterns } from '@/.velite'
import type { Metadata } from 'next'
import { PatternHeader } from '@/components/patterns/PatternHeader'
import { ArticleBody } from '@/components/patterns/ArticleBody'
import { RelatedPatterns } from '@/components/patterns/RelatedPatterns'
import { TableOfContents } from '@/components/layout/TableOfContents'
import { getPatternsByPillar, PILLAR_LABELS } from '@/lib/patterns'
import { OG_IMAGE, SITE_NAME, SITE_URL, editUrl } from '@/lib/site'

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
  const url = `${SITE_URL}/patterns/${pattern.slug}/`
  return {
    title: pattern.title,
    description: pattern.description,
    alternates: { canonical: url },
    openGraph: {
      type: 'article',
      title: `${pattern.title} · ${SITE_NAME}`,
      description: pattern.description,
      url,
      images: [OG_IMAGE],
    },
    twitter: { card: 'summary_large_image', title: pattern.title, description: pattern.description, images: [OG_IMAGE.url] },
  }
}

export default async function PatternPage({ params }: Props) {
  const { slug } = await params
  const pattern = patterns.find((p) => p.slug === slug.join('/'))

  if (!pattern) notFound()

  const siblings = getPatternsByPillar(pattern.pillar)
  const index = siblings.findIndex((p) => p.slug === pattern.slug)
  const prev = siblings[index - 1]
  const next = siblings[index + 1]

  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'TechArticle',
    headline: pattern.title,
    description: pattern.description,
    url: `${SITE_URL}/patterns/${pattern.slug}/`,
    articleSection: PILLAR_LABELS[pattern.pillar],
    keywords: pattern.tags.join(', '),
    isPartOf: { '@type': 'WebSite', name: SITE_NAME, url: SITE_URL },
  }

  return (
    <>
      <main className="min-w-0 flex-1" data-pagefind-body>
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
        <PatternHeader
          title={pattern.title}
          pillar={pattern.pillar}
          status={pattern.status}
          description={pattern.description}
          tags={pattern.tags}
          lastUpdated={pattern.last_updated}
          example={pattern.example}
        />
        <ArticleBody html={pattern.body} />
        {pattern.related && pattern.related.length > 0 && <RelatedPatterns related={pattern.related} />}

        <nav className="mt-12 grid sm:grid-cols-2 gap-3" aria-label="More in this pillar">
          {prev ? (
            <Link href={`/patterns/${prev.slug}`} className="rounded-lg border border-gray-200 dark:border-gray-800 p-4 hover:border-violet-300 dark:hover:border-violet-700 transition-colors">
              <span className="block text-xs text-gray-400 mb-1">← Previous</span>
              <span className="font-medium text-gray-900 dark:text-gray-100">{prev.title}</span>
            </Link>
          ) : (
            <span />
          )}
          {next && (
            <Link href={`/patterns/${next.slug}`} className="rounded-lg border border-gray-200 dark:border-gray-800 p-4 text-right hover:border-violet-300 dark:hover:border-violet-700 transition-colors">
              <span className="block text-xs text-gray-400 mb-1">Next →</span>
              <span className="font-medium text-gray-900 dark:text-gray-100">{next.title}</span>
            </Link>
          )}
        </nav>

        <p className="mt-10 text-sm text-gray-500 dark:text-gray-400">
          Spotted something wrong or have a production story?{' '}
          <a href={editUrl(`patterns/${pattern.slug}.md`)} target="_blank" rel="noopener noreferrer" className="text-[var(--accent)] hover:underline">
            Edit this page on GitHub
          </a>
          .
        </p>
      </main>

      <TableOfContents toc={pattern.toc} />
    </>
  )
}

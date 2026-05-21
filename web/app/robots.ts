import type { MetadataRoute } from 'next'

export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: '*', allow: '/' },
    sitemap: 'https://prajwalamte.github.io/AI-Engineering-Patterns/sitemap.xml',
  }
}

import { defineConfig, defineCollection, s } from 'velite'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'

const PILLARS = [
  'inference-and-serving',
  'data-patterns',
  'reliability',
  'retrieval-and-memory',
  'observability',
  'security-and-trust',
  'cost-and-efficiency',
  'governance',
  'graph-patterns',
  'evaluation-and-testing',
] as const

const patterns = defineCollection({
  name: 'Pattern',
  // .md only — all actual patterns are .md; pillar index pages are .mdx and excluded
  pattern: 'content/patterns/**/*.md',
  schema: s.object({
    title: s.string().min(3).max(100),
    pillar: s.enum(PILLARS),
    status: s.enum(['proposed', 'emerging', 'validated-in-production']),
    tags: s.array(s.string()),
    related: s.array(s.string()).optional(),
    description: s.string().optional(),
    contributors: s.array(s.string()).optional(),
    last_updated: s.string().optional(),
    sidebar: s.object({ order: s.number() }).optional(),
    // slug = pillar/pattern-name, e.g. retrieval-and-memory/hybrid-search
    slug: s.path().transform(p => p.replace(/^content\/patterns\//, '')),
    body: s.markdown(),
    toc: s.toc(),
  }),
})

const caseStudies = defineCollection({
  name: 'CaseStudy',
  pattern: 'content/case-studies/**/*.md',
  schema: s.object({
    title: s.string(),
    description: s.string().optional(),
    subject: s.string().optional(),
    patterns: s.array(s.string()).optional(),
    last_updated: s.string().optional(),
    slug: s.path().transform(p => p.replace(/^content\/case-studies\//, '')),
    body: s.markdown(),
    toc: s.toc(),
  }),
})

const guides = defineCollection({
  name: 'Guide',
  pattern: 'content/guides/**/*.md',
  schema: s.object({
    title: s.string(),
    description: s.string().optional(),
    slug: s.path().transform(p => p.replace(/^content\/guides\//, '')),
    body: s.markdown(),
    toc: s.toc(),
  }),
})

export default defineConfig({
  // root: '..' = repo root (one level above this config file in app/).
  // Content lives at repo-root/content/, output goes into app/.velite/ and app/public/static/.
  // Using the repo root avoids the Turbopack panic caused by a symlink pointing outside app/.
  root: '..',
  output: {
    // Paths are relative to root (repo root) → places output inside the app/ dir.
    data: 'app/.velite',
    assets: 'app/public/static',
    base: '/static/',
    name: '[name]-[hash:6].[ext]',
    clean: true,
  },
  collections: { patterns, caseStudies, guides },
  markdown: {
    remarkPlugins: [remarkMath],
    rehypePlugins: [rehypeKatex],
  },
})

import { defineConfig, defineCollection, s } from 'velite'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import rehypePrettyCode from 'rehype-pretty-code'
import rehypeSlug from 'rehype-slug'
import path from 'node:path'
import { remarkSiteLinks } from './lib/remark-site-links'

// velite runs from web/; content and examples live one level up.
const REPO_ROOT = path.resolve(process.cwd(), '..')
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? ''

const PILLARS = [
  'inference-and-serving',
  'data-patterns',
  'reliability',
  'retrieval-and-memory',
  'observability-and-evaluation',
  'security-and-trust',
  'cost-and-efficiency',
  'governance',
  'graph-patterns',
  'loop-engineering',
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
    // Repo-relative path to the runnable example, e.g. examples/reliability/circuit_breaker.py
    example: s.string().optional(),
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
  // root: '..' = repo root (one level above this config file in web/).
  // Content lives at repo-root/content/, output goes into .velite/ and public/static/ (relative to web/).
  root: '..',
  output: {
    // Paths are relative to the config file's directory (web/)
    data: '.velite',
    assets: 'public/static',
    base: '/static/',
    name: '[name]-[hash:6].[ext]',
    clean: true,
  },
  collections: { patterns, caseStudies, guides },
  markdown: {
    // Cross-reference links are rewritten to site routes, not copied as assets.
    copyLinkedFiles: false,
    remarkPlugins: [remarkMath, remarkSiteLinks({ root: REPO_ROOT, basePath: BASE_PATH })],
    rehypePlugins: [rehypeSlug, rehypeKatex, [rehypePrettyCode, { theme: 'github-dark', keepBackground: false }]],
  },
})

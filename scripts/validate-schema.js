import { execSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const ROOT = resolve(import.meta.dirname, '..')
const APP = resolve(ROOT, 'web')
const DATA = resolve(APP, '.velite')

// Run velite so the output is always fresh. Velite enforces the Zod schema;
// if any frontmatter field is invalid the build will exit non-zero here.
// Build without a base path so internal links are checked as plain routes.
console.log('Building content with Velite…')
try {
  execSync('npx velite build', {
    cwd: APP,
    stdio: 'inherit',
    env: { ...process.env, NEXT_PUBLIC_BASE_PATH: '' },
  })
} catch {
  console.error('\nVelite build failed — schema or frontmatter error above.')
  process.exit(1)
}

const load = (name) => JSON.parse(readFileSync(resolve(DATA, `${name}.json`), 'utf-8'))
const patterns = load('patterns')
const guides = load('guides')
const caseStudies = load('caseStudies')
console.log(`\n${patterns.length} pattern(s) indexed.\n`)

// Must stay in sync with resolveRelated() in web/lib/patterns.ts.
const normalize = (s) =>
  s.toLowerCase().replace(/[–—]/g, '-').replace(/[^a-z0-9\s-]/g, '').replace(/\s+/g, ' ').trim()
const titles = new Map(patterns.map((p) => [normalize(p.title), p]))

const routes = new Set(['/', '/patterns/', '/guides/', '/case-studies/', '/graph/'])
for (const p of patterns) routes.add(`/patterns/${p.slug}/`)
for (const g of guides) routes.add(`/guides/${g.slug}/`)
for (const c of caseStudies) routes.add(`/case-studies/${c.slug}/`)

let errors = 0
const fail = (msg) => {
  console.error(`FAIL ${msg}`)
  errors++
}

function checkLinks(where, html) {
  for (const [, href] of html.matchAll(/href="([^"]+)"/g)) {
    if (!href.startsWith('/') || href.startsWith('//')) continue
    const path = href.split('#')[0].split('?')[0]
    if (!routes.has(path)) fail(`${where}: broken internal link ${href}`)
  }
}

for (const p of patterns) {
  const before = errors
  const parts = p.slug.split('/')
  if (parts.length !== 2) fail(`${p.slug}: slug must be <pillar>/<name>`)
  else if (p.pillar !== parts[0]) fail(`${p.slug}: pillar "${p.pillar}" does not match directory "${parts[0]}"`)

  for (const name of p.related ?? []) {
    if (!titles.has(normalize(name))) fail(`${p.slug}: related "${name}" matches no pattern title`)
  }

  if (!p.example) fail(`${p.slug}: missing "example" (path to a runnable, tested example)`)
  else if (!existsSync(resolve(ROOT, p.example))) fail(`${p.slug}: example ${p.example} does not exist`)

  checkLinks(p.slug, p.body)
  if (errors === before) console.log(`PASS ${p.slug}`)
}

for (const g of guides) checkLinks(`guides/${g.slug}`, g.body)
for (const c of caseStudies) {
  checkLinks(`case-studies/${c.slug}`, c.body)
  for (const name of c.patterns ?? []) {
    if (!titles.has(normalize(name))) fail(`case-studies/${c.slug}: pattern "${name}" matches no pattern title`)
  }
}

if (errors) {
  console.error(`\n${errors} error(s).`)
  process.exit(1)
}

console.log(`\nAll ${patterns.length} pattern(s), ${guides.length} guide(s) and ${caseStudies.length} case stud(ies) passed.`)

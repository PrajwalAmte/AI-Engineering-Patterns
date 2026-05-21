import { execSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const APP = resolve(import.meta.dirname, '..', 'web')
const OUT = resolve(APP, '.velite', 'patterns.json')

// Run velite so the output is always fresh. Velite enforces the Zod schema;
// if any frontmatter field is invalid the build will exit non-zero here.
console.log('Building content with Velite…')
try {
  execSync('npx velite build', { cwd: APP, stdio: 'inherit' })
} catch {
  console.error('\nVelite build failed — schema or frontmatter error above.')
  process.exit(1)
}

const patterns = JSON.parse(readFileSync(OUT, 'utf-8'))
console.log(`\n${patterns.length} pattern(s) indexed.\n`)

// Cross-check: pillar field must match the directory segment of the slug.
let errors = 0
for (const p of patterns) {
  const parts = p.slug.split('/')
  if (parts.length !== 2) {
    console.error(`FAIL ${p.slug}: slug must be <pillar>/<name>`)
    errors++
    continue
  }
  const [dir] = parts
  if (p.pillar !== dir) {
    console.error(`FAIL ${p.slug}: pillar "${p.pillar}" does not match directory "${dir}"`)
    errors++
  } else {
    console.log(`PASS ${p.slug}`)
  }
}

if (errors) {
  console.error(`\n${errors} error(s). Fix the pillar fields above.`)
  process.exit(1)
}

console.log(`\nAll ${patterns.length} pattern(s) passed.`)


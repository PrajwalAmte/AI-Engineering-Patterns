// Copies each runnable example into its pattern page, so the code readers see
// is exactly the code CI tests. A pattern opts in with a marker block:
//
//   <!-- example: examples/reliability/circuit_breaker.py -->
//   ...anything, replaced on sync...
//   <!-- /example -->
//
// Usage: node scripts/sync-examples.js          rewrite pattern files
//        node scripts/sync-examples.js --check  exit 1 if any page is stale

import { readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'

const ROOT = resolve(import.meta.dirname, '..')
const PATTERNS = join(ROOT, 'content', 'patterns')
const check = process.argv.includes('--check')
const BLOCK = /<!-- example: (\S+) -->\n[\s\S]*?<!-- \/example -->/g

let stale = 0
for (const pillar of readdirSync(PATTERNS)) {
  for (const name of readdirSync(join(PATTERNS, pillar)).filter((f) => f.endsWith('.md'))) {
    const file = join(PATTERNS, pillar, name)
    const source = readFileSync(file, 'utf-8')
    const synced = source.replace(BLOCK, (_, examplePath) => {
      const code = readFileSync(join(ROOT, examplePath), 'utf-8').trimEnd()
      return `<!-- example: ${examplePath} -->\n\`\`\`python\n${code}\n\`\`\`\n<!-- /example -->`
    })
    if (synced === source) continue
    stale++
    if (check) console.error(`STALE ${pillar}/${name}`)
    else writeFileSync(file, synced)
  }
}

if (check && stale) {
  console.error(`\n${stale} pattern page(s) out of sync with examples/. Run: node scripts/sync-examples.js`)
  process.exit(1)
}
console.log(check ? 'Examples in sync.' : `Synced ${stale} pattern page(s).`)

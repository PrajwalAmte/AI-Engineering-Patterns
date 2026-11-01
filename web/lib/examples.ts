import fs from 'node:fs'
import path from 'node:path'

// Runs at build time only (static export), so the numbers on the site always
// match what's actually in examples/.
const EXAMPLES_DIR = path.resolve(process.cwd(), '..', 'examples')

export function countTests(): number {
  let total = 0
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name)
      if (entry.isDirectory()) walk(full)
      else if (/^test_.*\.py$/.test(entry.name)) {
        total += (fs.readFileSync(full, 'utf-8').match(/^def test_/gm) ?? []).length
      }
    }
  }
  try {
    walk(EXAMPLES_DIR)
  } catch {
    return 0
  }
  return total
}

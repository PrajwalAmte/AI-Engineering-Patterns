import path from 'node:path'

// Content is authored so it reads correctly on GitHub: cross-references are
// relative `.md` links and examples are repo paths. This plugin rewrites them
// into site routes at build time so the same markdown works in both places.

const REPO_URL = 'https://github.com/PrajwalAmte/AI-Engineering-Patterns'
const LEGACY_PREFIX = '/AI-Engineering-Patterns'

type Node = { type: string; url?: string; children?: Node[] }
type File = { path?: string }

export function remarkSiteLinks({ root, basePath }: { root: string; basePath: string }) {
  const contentDir = path.join(root, 'content')

  function rewrite(url: string, filePath: string): string {
    if (/^[a-z]+:|^#|^\/\//i.test(url)) return url

    const [target, hash = ''] = url.split('#')
    const suffix = hash ? `#${hash}` : ''

    if (target.endsWith('.md') || target.startsWith('examples/') || target.startsWith('../examples/')) {
      const abs = path.resolve(path.dirname(filePath), target)
      const rel = path.relative(contentDir, abs)

      if (rel.startsWith('..')) {
        // Outside content/: a file elsewhere in the repo, e.g. examples/.
        return `${REPO_URL}/blob/main/${path.relative(root, abs)}${suffix}`
      }
      const route = '/' + rel.replace(/\.md$/, '/')
      return `${basePath}${route}${suffix}`
    }

    if (target.startsWith('/')) {
      const clean = target.startsWith(LEGACY_PREFIX + '/') ? target.slice(LEGACY_PREFIX.length) : target
      return `${basePath}${clean}${suffix}`
    }

    return url
  }

  return () => (tree: Node, file: File) => {
    const walk = (node: Node) => {
      if ((node.type === 'link' || node.type === 'definition') && node.url && file.path) {
        node.url = rewrite(node.url, file.path)
      }
      node.children?.forEach(walk)
    }
    walk(tree)
  }
}

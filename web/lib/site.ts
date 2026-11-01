export const SITE_URL = 'https://prajwalamte.github.io/AI-Engineering-Patterns'
export const SITE_NAME = 'AI Engineering Patterns'
export const SITE_TAGLINE = 'Production LLM patterns you can run.'
export const SITE_DESCRIPTION =
  'Patterns for shipping LLM systems (caching, routing, guardrails, evals, agent loops), each with a runnable, tested Python reference implementation and an honest "when not to use it".'
export const REPO_URL = 'https://github.com/PrajwalAmte/AI-Engineering-Patterns'
// Rendered by app/og.png/route.tsx. Child pages that set openGraph must repeat it,
// because Next replaces (not merges) a parent's openGraph object.
export const OG_IMAGE = { url: `${SITE_URL}/og.png`, width: 1200, height: 630 }

export function exampleUrls(examplePath: string) {
  const testPath = examplePath.replace(/\/([^/]+)\.py$/, '/test_$1.py')
  return {
    code: `${REPO_URL}/blob/main/${examplePath}`,
    test: `${REPO_URL}/blob/main/${testPath}`,
    command: `cd examples && pytest ${testPath.replace(/^examples\//, '')}`,
  }
}

export function editUrl(contentPath: string) {
  return `${REPO_URL}/edit/main/content/${contentPath}`
}

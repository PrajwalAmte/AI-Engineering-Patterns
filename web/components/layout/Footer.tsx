import Link from 'next/link'
import { REPO_URL } from '@/lib/site'

export function Footer() {
  return (
    <footer className="border-t border-gray-200 dark:border-gray-800 mt-16">
      <div className="max-w-screen-xl mx-auto px-6 py-10 grid gap-8 sm:grid-cols-[2fr_1fr_1fr] text-sm">
        <div>
          <p className="font-semibold text-gray-900 dark:text-gray-100 mb-2">AI Engineering Patterns</p>
          <p className="text-gray-500 dark:text-gray-400 max-w-sm leading-relaxed">
            Production LLM patterns with runnable, tested reference implementations. Open source under the MIT license.
          </p>
        </div>
        <div className="flex flex-col gap-2 text-gray-500 dark:text-gray-400">
          <Link href="/patterns" className="hover:text-gray-900 dark:hover:text-gray-100">All patterns</Link>
          <Link href="/guides/decision-guide" className="hover:text-gray-900 dark:hover:text-gray-100">Decision guide</Link>
          <Link href="/guides/getting-started" className="hover:text-gray-900 dark:hover:text-gray-100">Getting started</Link>
          <Link href="/guides/glossary" className="hover:text-gray-900 dark:hover:text-gray-100">Glossary</Link>
        </div>
        <div className="flex flex-col gap-2 text-gray-500 dark:text-gray-400">
          <a href={REPO_URL} target="_blank" rel="noopener noreferrer" className="hover:text-gray-900 dark:hover:text-gray-100">GitHub</a>
          <a href={`${REPO_URL}/tree/main/examples`} target="_blank" rel="noopener noreferrer" className="hover:text-gray-900 dark:hover:text-gray-100">Example code</a>
          <a href={`${REPO_URL}/blob/main/CONTRIBUTING.md`} target="_blank" rel="noopener noreferrer" className="hover:text-gray-900 dark:hover:text-gray-100">Contribute</a>
          <a href={`${REPO_URL}/issues/new/choose`} target="_blank" rel="noopener noreferrer" className="hover:text-gray-900 dark:hover:text-gray-100">Report an issue</a>
        </div>
      </div>
    </footer>
  )
}

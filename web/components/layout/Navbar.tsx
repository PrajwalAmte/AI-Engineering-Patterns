import Link from 'next/link'
import { DarkModeToggle } from './DarkModeToggle'
import { Search } from './Search'
import { REPO_URL } from '@/lib/site'

const LINKS = [
  { href: '/patterns', label: 'Patterns' },
  { href: '/guides/decision-guide', label: 'Decision guide' },
  { href: '/case-studies', label: 'Case studies' },
  { href: '/graph', label: 'Graph' },
  { href: '/guides', label: 'Guides' },
]

const linkClass =
  'px-3 py-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-gray-50 transition-colors'

export function Navbar() {
  return (
    <header className="sticky top-0 z-40 w-full border-b border-gray-200 dark:border-gray-800 bg-white/90 dark:bg-gray-950/90 backdrop-blur-sm">
      <div className="max-w-screen-2xl mx-auto px-4 flex items-center justify-between h-14 gap-3">
        <Link
          href="/"
          className="flex items-center gap-2 font-semibold text-gray-900 dark:text-gray-50 hover:opacity-80 transition-opacity shrink-0"
        >
          <span className="text-[var(--accent)]">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </svg>
          </span>
          <span className="hidden sm:inline">AI Engineering Patterns</span>
          <span className="sm:hidden">AIEP</span>
        </Link>

        <nav className="hidden lg:flex items-center gap-1 text-sm text-gray-600 dark:text-gray-400">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} className={linkClass}>
              {l.label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-1.5">
          <Search />
          <a
            href={REPO_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="hidden sm:inline-flex items-center gap-1.5 h-9 rounded-md border border-gray-200 dark:border-gray-700 px-3 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
              <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0 1 12 6.844a9.59 9.59 0 0 1 2.504.337c1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.02 10.02 0 0 0 22 12.017C22 6.484 17.522 2 12 2z" />
            </svg>
            Star
          </a>
          <DarkModeToggle />

          {/* Mobile menu: no JS needed */}
          <details className="lg:hidden relative">
            <summary
              className="list-none flex items-center justify-center w-9 h-9 rounded-md text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 cursor-pointer [&::-webkit-details-marker]:hidden"
              aria-label="Open menu"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                <path d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </summary>
            <nav className="absolute right-0 mt-2 w-56 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 shadow-lg p-2 flex flex-col text-sm text-gray-700 dark:text-gray-300">
              {LINKS.map((l) => (
                <Link key={l.href} href={l.href} className={linkClass}>
                  {l.label}
                </Link>
              ))}
              <a href={REPO_URL} target="_blank" rel="noopener noreferrer" className={linkClass}>
                GitHub
              </a>
            </nav>
          </details>
        </div>
      </div>
    </header>
  )
}

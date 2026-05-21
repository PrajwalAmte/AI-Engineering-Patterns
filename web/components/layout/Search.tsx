'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'

type PagefindHit = {
  url: string
  meta: { title: string }
  excerpt: string
}

type PagefindAPI = {
  search: (q: string) => Promise<{ results: Array<{ data: () => Promise<PagefindHit> }> }>
}

// Keep only <mark> tags from pagefind excerpts; strip everything else.
// Pagefind generates these from our own indexed content, but we whitelist
// only the <mark> tag to be safe.
function safeExcerpt(html: string): string {
  return html.replace(/<(?!\/?(mark)(\s|>))[^>]+>/gi, '')
}

export function Search() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<PagefindHit[]>([])
  const inputRef = useRef<HTMLInputElement>(null)

  const close = useCallback(() => {
    setOpen(false)
    setQuery('')
    setHits([])
  }, [])

  // ⌘K / Ctrl+K opens search
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setOpen(true)
      }
      if (e.key === 'Escape') close()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [close])

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 30)
  }, [open])

  useEffect(() => {
    if (!query.trim()) { setHits([]); return }
    const id = setTimeout(async () => {
      try {
        const base = process.env.NEXT_PUBLIC_BASE_PATH ?? ''
        // Use new Function to prevent Turbopack from trying to statically bundle
        // /pagefind/pagefind.js — it is generated at build time by the pagefind CLI.
        const dynamicImport = new Function('url', 'return import(url)')
        const pf = (await dynamicImport(`${base}/pagefind/pagefind.js`)) as PagefindAPI
        const res = await pf.search(query)
        const data = await Promise.all(res.results.slice(0, 8).map((r) => r.data()))
        setHits(data)
      } catch {
        setHits([])
      }
    }, 200)
    return () => clearTimeout(id)
  }, [query])

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        aria-label="Search (⌘K)"
        className="hidden sm:flex items-center gap-2 rounded-md border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 px-3 h-8 text-sm text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors min-w-[160px]"
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
          <circle cx="11" cy="11" r="8" />
          <path d="m21 21-4.35-4.35" />
        </svg>
        <span>Search</span>
        <kbd className="ml-auto text-[10px] font-mono border border-gray-300 dark:border-gray-600 rounded px-1 opacity-60">
          ⌘K
        </kbd>
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center pt-[10vh] px-4 bg-black/40"
          onClick={close}
        >
          <div
            className="w-full max-w-lg rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 shadow-2xl overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3 px-4 border-b border-gray-200 dark:border-gray-700">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-gray-400 shrink-0" aria-hidden>
                <circle cx="11" cy="11" r="8" />
                <path d="m21 21-4.35-4.35" />
              </svg>
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search patterns, guides…"
                className="flex-1 bg-transparent py-4 text-sm text-gray-900 dark:text-gray-50 placeholder:text-gray-400 outline-none"
              />
              <button
                onClick={close}
                className="shrink-0 text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
              >
                Esc
              </button>
            </div>

            {hits.length > 0 && (
              <ul className="max-h-80 overflow-y-auto divide-y divide-gray-100 dark:divide-gray-800">
                {hits.map((hit) => (
                  <li key={hit.url}>
                    <Link
                      href={hit.url}
                      onClick={close}
                      className="block px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                    >
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-0.5 truncate">
                        {hit.meta.title}
                      </p>
                      <p
                        className="text-xs text-gray-500 dark:text-gray-400 line-clamp-2 [&_mark]:bg-yellow-100 [&_mark]:dark:bg-yellow-900/40 [&_mark]:text-inherit [&_mark]:font-medium"
                        dangerouslySetInnerHTML={{ __html: safeExcerpt(hit.excerpt) }}
                      />
                    </Link>
                  </li>
                ))}
              </ul>
            )}

            {query.trim() && hits.length === 0 && (
              <p className="px-4 py-8 text-sm text-center text-gray-400">
                No results for &ldquo;{query}&rdquo;
              </p>
            )}
          </div>
        </div>
      )}
    </>
  )
}

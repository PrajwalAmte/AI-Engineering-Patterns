'use client'

import { useEffect, useState } from 'react'

interface TocEntry {
  title: string
  url: string
  items: TocEntry[]
}

interface Props {
  toc: TocEntry[]
}

export function TableOfContents({ toc }: Props) {
  const [activeId, setActiveId] = useState<string>('')

  useEffect(() => {
    const headingIds = toc.flatMap((e) => [
      e.url.slice(1),
      ...e.items.map((i) => i.url.slice(1)),
    ])

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveId(entry.target.id)
            break
          }
        }
      },
      { rootMargin: '0px 0px -70% 0px', threshold: 0 },
    )

    headingIds.forEach((id) => {
      const el = document.getElementById(id)
      if (el) observer.observe(el)
    })

    return () => observer.disconnect()
  }, [toc])

  if (toc.length === 0) return null

  return (
    <aside className="hidden xl:block w-52 shrink-0">
      <div className="sticky top-20 max-h-[calc(100vh-5rem)] overflow-y-auto pl-4 pb-12">
        <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
          On this page
        </p>
        <nav>
          <ul className="space-y-1 text-sm">
            {toc.map((entry) => {
              const id = entry.url.slice(1)
              const isActive = activeId === id
              return (
                <li key={entry.url}>
                  <a
                    href={entry.url}
                    className={`block py-0.5 transition-colors ${
                      isActive
                        ? 'text-[var(--accent)] font-medium'
                        : 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-50'
                    }`}
                  >
                    {entry.title}
                  </a>
                  {entry.items.length > 0 && (
                    <ul className="ml-3 mt-1 space-y-1">
                      {entry.items.map((sub) => {
                        const subId = sub.url.slice(1)
                        const subActive = activeId === subId
                        return (
                          <li key={sub.url}>
                            <a
                              href={sub.url}
                              className={`block py-0.5 transition-colors ${
                                subActive
                                  ? 'text-[var(--accent)] font-medium'
                                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-50'
                              }`}
                            >
                              {sub.title}
                            </a>
                          </li>
                        )
                      })}
                    </ul>
                  )}
                </li>
              )
            })}
          </ul>
        </nav>
      </div>
    </aside>
  )
}

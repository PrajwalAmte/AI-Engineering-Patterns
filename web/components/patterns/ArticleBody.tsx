'use client'

import { useEffect, useRef } from 'react'

interface Props {
  html: string
}

export function ArticleBody({ html }: Props) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current) return
    const diagrams = ref.current.querySelectorAll<HTMLElement>('pre.mermaid')
    if (!diagrams.length) return

    const isDark = document.documentElement.classList.contains('dark')

    import('mermaid').then(({ default: mermaid }) => {
      mermaid.initialize({
        startOnLoad: false,
        theme: isDark ? 'dark' : 'default',
        securityLevel: 'strict',
        fontFamily: 'var(--font-geist-sans), system-ui, sans-serif',
      })
      mermaid.run({ nodes: Array.from(diagrams) })
    })
  }, [html])

  return (
    <div
      ref={ref}
      className="
        prose prose-gray dark:prose-invert max-w-none
        prose-headings:font-bold prose-headings:tracking-tight
        prose-h2:text-2xl prose-h2:mt-10 prose-h2:mb-4 prose-h2:border-l-4 prose-h2:border-[var(--accent)] prose-h2:pl-3
        prose-h3:text-lg prose-h3:mt-6 prose-h3:mb-2 prose-h3:text-violet-700 dark:prose-h3:text-violet-300
        prose-p:leading-relaxed
        prose-code:before:content-none prose-code:after:content-none prose-code:text-[0.875em] prose-code:font-medium
        prose-code:bg-gray-100 prose-code:dark:bg-gray-800 prose-code:rounded prose-code:px-1 prose-code:py-0.5
        prose-pre:bg-gray-900 prose-pre:dark:bg-gray-950 prose-pre:text-gray-100 prose-pre:rounded-lg prose-pre:border prose-pre:border-gray-800
        prose-a:text-violet-600 dark:prose-a:text-violet-400 prose-a:no-underline hover:prose-a:underline
        prose-strong:text-gray-900 dark:prose-strong:text-gray-50
        prose-table:text-sm
        prose-th:bg-gray-50 dark:prose-th:bg-gray-900
        [&_pre.mermaid]:bg-transparent [&_pre.mermaid]:p-0 [&_pre.mermaid]:border-0
        [&_.katex-display]:overflow-x-auto
      "
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

'use client'

import { useState } from 'react'

export function CopyCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false)

  return (
    <div className="flex items-center gap-2 rounded-md bg-gray-950 px-3 py-2 font-mono text-[13px] text-gray-200 overflow-x-auto">
      <span className="text-gray-500 select-none">$</span>
      <code className="flex-1 whitespace-nowrap">{command}</code>
      <button
        type="button"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(command)
            setCopied(true)
            setTimeout(() => setCopied(false), 1500)
          } catch {
            /* clipboard unavailable; the text is selectable anyway */
          }
        }}
        className="shrink-0 rounded px-2 py-0.5 text-xs font-sans text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
        aria-label="Copy command"
      >
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  )
}

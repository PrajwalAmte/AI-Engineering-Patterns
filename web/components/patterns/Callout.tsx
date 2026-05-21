import type { ReactNode } from 'react'

type CalloutType = 'info' | 'warning' | 'production' | 'cost'

interface Props {
  type: CalloutType
  title?: string
  children: ReactNode
}

const CONFIG: Record<CalloutType, { border: string; bg: string; title: string; icon: string }> = {
  info: {
    border: 'border-blue-500',
    bg: 'bg-blue-50 dark:bg-blue-950/20',
    title: 'text-blue-700 dark:text-blue-300',
    icon: 'ℹ',
  },
  warning: {
    border: 'border-yellow-500',
    bg: 'bg-yellow-50 dark:bg-yellow-950/20',
    title: 'text-yellow-700 dark:text-yellow-300',
    icon: '⚠',
  },
  production: {
    border: 'border-green-500',
    bg: 'bg-green-50 dark:bg-green-950/20',
    title: 'text-green-700 dark:text-green-300',
    icon: '⚙',
  },
  cost: {
    border: 'border-orange-500',
    bg: 'bg-orange-50 dark:bg-orange-950/20',
    title: 'text-orange-700 dark:text-orange-300',
    icon: '$',
  },
}

export function Callout({ type, title, children }: Props) {
  const c = CONFIG[type]
  return (
    <div
      role="note"
      className={`my-6 rounded-r-md border-l-4 px-4 py-3.5 ${c.border} ${c.bg}`}
    >
      {title && (
        <p className={`mb-1 text-sm font-semibold ${c.title}`}>
          <span aria-hidden className="mr-1.5">{c.icon}</span>
          {title}
        </p>
      )}
      <div className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed [&>p]:m-0">
        {children}
      </div>
    </div>
  )
}

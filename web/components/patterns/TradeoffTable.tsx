interface Props {
  pros: string[]
  cons: string[]
}

export function TradeoffTable({ pros, cons }: Props) {
  return (
    <div className="my-6 grid grid-cols-2 gap-px rounded-lg overflow-hidden border border-gray-200 dark:border-gray-700 text-sm">
      <div className="bg-green-50 dark:bg-green-950/20 p-4">
        <p className="font-semibold text-green-700 dark:text-green-300 mb-2">Benefits</p>
        <ul className="space-y-1.5">
          {pros.map((pro, i) => (
            <li key={i} className="flex gap-2 text-gray-700 dark:text-gray-300">
              <span className="text-green-500 shrink-0 mt-0.5" aria-hidden>+</span>
              {pro}
            </li>
          ))}
        </ul>
      </div>
      <div className="bg-red-50 dark:bg-red-950/20 p-4">
        <p className="font-semibold text-red-700 dark:text-red-300 mb-2">Trade-offs</p>
        <ul className="space-y-1.5">
          {cons.map((con, i) => (
            <li key={i} className="flex gap-2 text-gray-700 dark:text-gray-300">
              <span className="text-red-500 shrink-0 mt-0.5" aria-hidden>−</span>
              {con}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

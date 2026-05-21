import { PatternGraph } from '@/components/graph/PatternGraph'

export const metadata = {
  title: 'Pattern Graph | AI Engineering Patterns',
  description: 'Interactive force-directed graph of all AI engineering patterns and their relationships.',
}

export default function GraphPage() {
  return (
    <main className="max-w-screen-xl mx-auto px-6 py-12">
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-gray-900 dark:text-gray-50 mb-2">
          Pattern Graph
        </h1>
        <p className="text-gray-500 dark:text-gray-400">
          Interactive force-directed graph showing relationships between patterns. Drag nodes to explore, click to navigate.
        </p>
      </div>
      <PatternGraph />
    </main>
  )
}

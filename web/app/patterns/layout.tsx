import { Sidebar } from '@/components/layout/Sidebar'

export default function PatternsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="max-w-screen-2xl mx-auto px-4 py-10 flex gap-8">
      <Sidebar />
      {children}
    </div>
  )
}

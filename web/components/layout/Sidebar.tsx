import { SidebarNav } from './SidebarNav'

export function Sidebar() {
  return (
    <aside className="hidden lg:block w-64 shrink-0">
      <div className="sticky top-20 max-h-[calc(100vh-5rem)] overflow-y-auto pr-4 pb-12">
        <SidebarNav />
      </div>
    </aside>
  )
}

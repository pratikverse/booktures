'use client'

import { AppSidebar } from '@/components/app-sidebar'
import { AppTopBar } from '@/components/app-top-bar'

interface AppShellProps {
  children: React.ReactNode
  showTopBar?: boolean
  onSearch?: (query: string) => void
  stats?: {
    totalBooks: number
    queuedJobs: number
    failedJobs: number
  }
  onDataChanged?: () => void | Promise<void>
}

export function AppShell({
  children,
  showTopBar = true,
  onSearch,
  stats,
  onDataChanged,
}: AppShellProps) {
  return (
    <div className="min-h-screen bg-background">
      <AppSidebar />
      <div className="pl-56">
        {showTopBar && <AppTopBar stats={stats} onSearch={onSearch} onDataChanged={onDataChanged} />}
        <main className="min-h-[calc(100vh-3.5rem)]">
          {children}
        </main>
      </div>
    </div>
  )
}

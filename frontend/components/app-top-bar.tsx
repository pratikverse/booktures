'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Search, Upload, BookOpen, Clock, AlertCircle } from 'lucide-react'
import { UploadDialog } from '@/components/upload-dialog'

interface AppTopBarProps {
  stats?: {
    totalBooks: number
    queuedJobs: number
    failedJobs: number
  }
  onSearch?: (query: string) => void
  onDataChanged?: () => void | Promise<void>
}

export function AppTopBar({ stats, onSearch, onDataChanged }: AppTopBarProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [uploadOpen, setUploadOpen] = useState(false)

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    onSearch?.(searchQuery)
  }

  return (
    <>
      <header className="sticky top-0 z-30 flex h-14 items-center gap-4 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 px-6">
        {/* Search */}
        <form onSubmit={handleSearch} className="flex-1 max-w-md">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="search"
              placeholder="Search books..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 bg-secondary border-0 focus-visible:ring-1"
            />
          </div>
        </form>

        {/* Stats Chips */}
        {stats && (
          <div className="hidden md:flex items-center gap-2">
            <div className="flex items-center gap-1.5 rounded-md bg-secondary px-2.5 py-1 text-xs">
              <BookOpen className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="text-muted-foreground">{stats.totalBooks} books</span>
            </div>
            {stats.queuedJobs > 0 && (
              <div className="flex items-center gap-1.5 rounded-md bg-status-image-queued/10 px-2.5 py-1 text-xs">
                <Clock className="h-3.5 w-3.5 text-status-image-queued" />
                <span className="text-status-image-queued">{stats.queuedJobs} queued</span>
              </div>
            )}
            {stats.failedJobs > 0 && (
              <div className="flex items-center gap-1.5 rounded-md bg-status-failed/10 px-2.5 py-1 text-xs">
                <AlertCircle className="h-3.5 w-3.5 text-status-failed" />
                <span className="text-status-failed">{stats.failedJobs} failed</span>
              </div>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2">
          <Button size="sm" onClick={() => setUploadOpen(true)}>
            <Upload className="mr-2 h-4 w-4" />
            Upload PDF
          </Button>
        </div>
      </header>

      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} onSuccess={onDataChanged} />
    </>
  )
}

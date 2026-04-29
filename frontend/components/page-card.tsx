'use client'

import { cn } from '@/lib/utils'
import { StatusBadge } from '@/components/status-badge'
import { Button } from '@/components/ui/button'
import { Image as ImageIcon, Play, Clock } from 'lucide-react'
import type { Page } from '@/lib/types'

interface PageCardProps {
  page: Page
  isSelected?: boolean
  onSelect?: (page: Page) => void
  onGenerate?: (pageNumber: number) => void
  className?: string
}

function formatTime(dateString?: string) {
  if (!dateString) return null
  const date = new Date(dateString)
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function PageCard({
  page,
  isSelected,
  onSelect,
  onGenerate,
  className,
}: PageCardProps) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onSelect?.(page)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onSelect?.(page)
        }
      }}
      className={cn(
        'group relative flex flex-col rounded-xl border bg-card p-3 text-left transition-all',
        'hover:bg-accent/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        isSelected
          ? 'border-ring ring-1 ring-ring bg-accent/20'
          : 'border-border',
        className
      )}
    >
      {/* Image Preview Area */}
      <div className="relative aspect-[3/4] w-full rounded-lg bg-secondary mb-3 overflow-hidden">
        {page.imageUrl ? (
          <img
            src={page.imageUrl}
            alt={`Generated illustration for page ${page.pageNumber}`}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center">
            <ImageIcon className="h-8 w-8 text-muted-foreground/30" />
          </div>
        )}

        {/* Quick Action Overlay */}
        {page.status !== 'image_ready' && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/60 opacity-0 group-hover:opacity-100 transition-opacity">
            <Button
              size="sm"
              onClick={(e) => {
                e.stopPropagation()
                onGenerate?.(page.pageNumber)
              }}
              className="h-8"
            >
              <Play className="mr-1 h-3 w-3" />
              Generate
            </Button>
          </div>
        )}
      </div>

      {/* Page Info */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-foreground">
            Page {page.pageNumber}
          </span>
        </div>

        <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
          {page.textExcerpt}
        </p>

        <div className="flex items-center justify-between gap-2">
          <StatusBadge status={page.status} />
          {page.lastGeneratedAt && (
            <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
              <Clock className="h-2.5 w-2.5" />
              {formatTime(page.lastGeneratedAt)}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

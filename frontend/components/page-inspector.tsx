'use client'

import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { StatusBadge } from '@/components/status-badge'
import { InspectorSkeleton } from '@/components/loading-skeleton'
import {
  Play,
  RefreshCw,
  Info,
  Image as ImageIcon,
  AlertTriangle,
  X,
  Clock,
} from 'lucide-react'
import type { Page } from '@/lib/types'

interface PageInspectorProps {
  page: Page | null
  isLoading?: boolean
  onClose?: () => void
  onGenerate?: (pageNumber: number) => void
  onRegenerate?: (pageNumber: number) => void
  onViewMetadata?: (pageNumber: number) => void
  className?: string
}

function formatDateTime(dateString?: string) {
  if (!dateString) return null
  const date = new Date(dateString)
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function PageInspector({
  page,
  isLoading,
  onClose,
  onGenerate,
  onRegenerate,
  onViewMetadata,
  className,
}: PageInspectorProps) {
  if (isLoading) {
    return (
      <div className={cn('border-l border-border bg-card', className)}>
        <InspectorSkeleton />
      </div>
    )
  }

  if (!page) {
    return (
      <div
        className={cn(
          'border-l border-border bg-card flex items-center justify-center',
          className
        )}
      >
        <div className="text-center px-6">
          <ImageIcon className="h-12 w-12 text-muted-foreground/30 mx-auto mb-3" />
          <p className="text-sm text-muted-foreground">
            Select a page to view details
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className={cn('border-l border-border bg-card overflow-y-auto', className)}>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-lg font-semibold text-foreground">
              Page {page.pageNumber}
            </h3>
            {page.lastGeneratedAt && (
              <p className="text-xs text-muted-foreground flex items-center gap-1 mt-1">
                <Clock className="h-3 w-3" />
                Last generated {formatDateTime(page.lastGeneratedAt)}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge status={page.status} />
            {onClose && (
              <Button
                variant="ghost"
                size="icon"
                onClick={onClose}
                className="h-7 w-7"
              >
                <X className="h-4 w-4" />
                <span className="sr-only">Close inspector</span>
              </Button>
            )}
          </div>
        </div>

        {/* Error Message */}
        {page.status === 'failed' && page.errorMessage && (
          <div className="rounded-lg bg-status-failed/10 border border-status-failed/20 p-3">
            <div className="flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 text-status-failed mt-0.5 shrink-0" />
              <div>
                <p className="text-sm font-medium text-status-failed">
                  Generation Failed
                </p>
                <p className="text-xs text-status-failed/80 mt-0.5">
                  {page.errorMessage}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Text Excerpt */}
        <div className="space-y-2">
          <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Text Excerpt
          </h4>
          <div className="rounded-lg bg-secondary p-3 max-h-32 overflow-y-auto">
            <p className="text-sm text-foreground leading-relaxed">
              {page.textExcerpt}
            </p>
          </div>
        </div>

        {/* Generated Prompt */}
        {page.prompt && (
          <div className="space-y-2">
            <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Generated Prompt
            </h4>
            <div className="rounded-lg bg-secondary p-3 max-h-28 overflow-y-auto">
              <pre className="text-xs text-foreground font-mono whitespace-pre-wrap leading-relaxed">
                {page.prompt}
              </pre>
            </div>
          </div>
        )}

        {/* Image Preview */}
        <div className="space-y-2">
          <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Image Preview
          </h4>
          <div className="aspect-square rounded-xl bg-secondary flex items-center justify-center overflow-hidden">
            {page.imageUrl ? (
              <img
                src={page.imageUrl}
                alt={`Generated illustration for page ${page.pageNumber}`}
                className="h-full w-full object-cover"
              />
            ) : (
              <div className="text-center">
                <ImageIcon className="h-12 w-12 text-muted-foreground/30 mx-auto mb-2" />
                <p className="text-xs text-muted-foreground">No image generated</p>
              </div>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-2">
          {page.status === 'image_ready' ? (
            <>
              <Button
                variant="outline"
                className="flex-1"
                onClick={() => onRegenerate?.(page.pageNumber)}
              >
                <RefreshCw className="mr-2 h-4 w-4" />
                Regenerate
              </Button>
              <Button
                variant="outline"
                onClick={() => onViewMetadata?.(page.pageNumber)}
              >
                <Info className="h-4 w-4" />
                <span className="sr-only">View metadata</span>
              </Button>
            </>
          ) : (
            <Button
              className="flex-1"
              onClick={() => onGenerate?.(page.pageNumber)}
            >
              <Play className="mr-2 h-4 w-4" />
              Generate Image
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

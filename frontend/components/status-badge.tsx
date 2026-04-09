'use client'

import { cn } from '@/lib/utils'
import type { PageStatus, BookStatus, JobStatus } from '@/lib/types'

type StatusType = PageStatus | BookStatus | JobStatus

interface StatusBadgeProps {
  status: StatusType
  className?: string
}

const statusConfig: Record<StatusType, { label: string; className: string }> = {
  // Page statuses
  prompt_ready: {
    label: 'Prompt Ready',
    className: 'bg-status-prompt-ready/15 text-status-prompt-ready border-status-prompt-ready/30',
  },
  image_queued: {
    label: 'Image Queued',
    className: 'bg-status-image-queued/15 text-status-image-queued border-status-image-queued/30',
  },
  image_ready: {
    label: 'Image Ready',
    className: 'bg-status-image-ready/15 text-status-image-ready border-status-image-ready/30',
  },
  // Book statuses
  processing: {
    label: 'Processing',
    className: 'bg-status-image-queued/15 text-status-image-queued border-status-image-queued/30',
  },
  ready: {
    label: 'Ready',
    className: 'bg-status-image-ready/15 text-status-image-ready border-status-image-ready/30',
  },
  partial: {
    label: 'Partial',
    className: 'bg-status-prompt-ready/15 text-status-prompt-ready border-status-prompt-ready/30',
  },
  // Job statuses
  queued: {
    label: 'Queued',
    className: 'bg-muted text-muted-foreground border-border',
  },
  running: {
    label: 'Running',
    className: 'bg-status-prompt-ready/15 text-status-prompt-ready border-status-prompt-ready/30',
  },
  paused: {
    label: 'Paused',
    className: 'bg-status-image-queued/15 text-status-image-queued border-status-image-queued/30',
  },
  canceled: {
    label: 'Canceled',
    className: 'bg-muted text-muted-foreground border-border',
  },
  completed: {
    label: 'Completed',
    className: 'bg-status-image-ready/15 text-status-image-ready border-status-image-ready/30',
  },
  // Shared
  failed: {
    label: 'Failed',
    className: 'bg-status-failed/15 text-status-failed border-status-failed/30',
  },
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const config = statusConfig[status]

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium',
        config.className,
        className
      )}
    >
      {config.label}
    </span>
  )
}

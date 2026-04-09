'use client'

import { cn } from '@/lib/utils'

interface JobProgressProps {
  progress: number
  status: 'queued' | 'running' | 'paused' | 'canceled' | 'completed' | 'failed'
  className?: string
}

export function JobProgress({ progress, status, className }: JobProgressProps) {
  const getProgressColor = () => {
    switch (status) {
      case 'completed':
        return 'bg-status-image-ready'
      case 'failed':
        return 'bg-status-failed'
      case 'running':
        return 'bg-status-prompt-ready'
      case 'paused':
        return 'bg-status-image-queued'
      default:
        return 'bg-muted-foreground'
    }
  }

  return (
    <div className={cn('flex items-center gap-3', className)}>
      <div className="h-1.5 flex-1 rounded-full bg-secondary overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all duration-300', getProgressColor())}
          style={{ width: `${progress}%` }}
        />
      </div>
      <span className="text-xs font-mono text-muted-foreground w-10 text-right">
        {progress}%
      </span>
    </div>
  )
}

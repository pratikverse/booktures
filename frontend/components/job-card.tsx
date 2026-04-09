'use client'

import Link from 'next/link'
import { cn } from '@/lib/utils'
import { StatusBadge } from '@/components/status-badge'
import { JobProgress } from '@/components/job-progress'
import { Button } from '@/components/ui/button'
import { BookOpen, FileText, Clock, AlertTriangle, Pause, Play, X } from 'lucide-react'
import type { Job } from '@/lib/types'

interface JobCardProps {
  job: Job
  className?: string
  actionState?: 'idle' | 'pause' | 'resume' | 'cancel'
  onPause?: (job: Job) => void | Promise<void>
  onResume?: (job: Job) => void | Promise<void>
  onCancel?: (job: Job) => void | Promise<void>
}

function formatDateTime(dateString?: string | null) {
  if (!dateString) return 'Not started yet'
  const date = new Date(dateString)
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function getRelativeTime(dateString?: string | null) {
  if (!dateString) return 'just now'
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffMins < 1) return 'just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  return `${diffDays}d ago`
}

export function JobCard({ job, className, actionState = 'idle', onPause, onResume, onCancel }: JobCardProps) {
  const Icon = job.type === 'full_book' ? BookOpen : FileText
  const canPause = job.status === 'queued' || job.status === 'running'
  const canResume = job.status === 'paused'
  const canCancel = job.status === 'queued' || job.status === 'running' || job.status === 'paused'

  return (
    <div
      className={cn(
        'rounded-xl border border-border bg-card p-4 transition-colors hover:bg-accent/30',
        className
      )}
    >
      <div className="flex items-start gap-4">
        <div
          className={cn(
            'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg',
            job.status === 'running'
              ? 'bg-status-prompt-ready/10'
              : job.status === 'paused'
                ? 'bg-status-image-queued/10'
                : job.status === 'failed'
                  ? 'bg-status-failed/10'
                  : job.status === 'completed'
                    ? 'bg-status-image-ready/10'
                    : 'bg-secondary'
          )}
        >
          <Icon
            className={cn(
              'h-5 w-5',
              job.status === 'running'
                ? 'text-status-prompt-ready'
                : job.status === 'paused'
                  ? 'text-status-image-queued'
                  : job.status === 'failed'
                    ? 'text-status-failed'
                    : job.status === 'completed'
                      ? 'text-status-image-ready'
                      : 'text-muted-foreground'
            )}
          />
        </div>

        <div className="min-w-0 flex-1">
          <div className="mb-1 flex items-start justify-between gap-3">
            <div>
              <Link
                href={`/books/${job.bookId}`}
                className="rounded text-sm font-semibold text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {job.bookTitle}
              </Link>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {job.type === 'full_book' ? 'Full book generation' : `Page ${job.pageNumber} generation`}
                <span className="mx-1.5">-</span>
                <span className="font-mono">{job.id}</span>
              </p>
            </div>
            <StatusBadge status={job.status} />
          </div>

          {(job.status === 'running' || job.status === 'queued' || job.status === 'paused') && (
            <div className="mt-3">
              <JobProgress progress={job.progress} status={job.status} />
            </div>
          )}

          {job.status === 'failed' && job.errorMessage && (
            <div className="mt-3 flex items-start gap-2 rounded-lg bg-status-failed/10 p-2">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-status-failed" />
              <p className="text-xs text-status-failed">{job.errorMessage}</p>
            </div>
          )}

          <div className="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              Started {formatDateTime(job.startedAt)}
            </span>
            <span>Updated {getRelativeTime(job.updatedAt)}</span>
          </div>

          {(canPause || canResume || canCancel) && (
            <div className="mt-4 flex flex-wrap items-center gap-2">
              {canPause && onPause && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={actionState !== 'idle'}
                  onClick={() => void onPause(job)}
                >
                  <Pause className="mr-1.5 h-3.5 w-3.5" />
                  {job.status === 'running' ? 'Pause' : 'Hold'}
                </Button>
              )}
              {canResume && onResume && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={actionState !== 'idle'}
                  onClick={() => void onResume(job)}
                >
                  <Play className="mr-1.5 h-3.5 w-3.5" />
                  Resume
                </Button>
              )}
              {canCancel && onCancel && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={actionState !== 'idle'}
                  onClick={() => void onCancel(job)}
                >
                  <X className="mr-1.5 h-3.5 w-3.5" />
                  Cancel
                </Button>
              )}
              {actionState !== 'idle' && (
                <span className="text-xs text-muted-foreground">
                  {actionState === 'pause' && 'Sending pause request...'}
                  {actionState === 'resume' && 'Resuming job...'}
                  {actionState === 'cancel' && 'Canceling job...'}
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

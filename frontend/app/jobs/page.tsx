'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { AppShell } from '@/components/app-shell'
import { JobCard } from '@/components/job-card'
import { EmptyState } from '@/components/empty-state'
import { ErrorState } from '@/components/error-state'
import { JobListSkeleton } from '@/components/loading-skeleton'
import { Clock } from 'lucide-react'
import { cancelJob, listBooks, listJobs, pauseJob, resumeJob } from '@/lib/api'
import type { Job } from '@/lib/types'

type JobActionState = 'idle' | 'pause' | 'resume' | 'cancel'

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [booksCount, setBooksCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState(new Date())
  const [jobActions, setJobActions] = useState<Record<number, JobActionState>>({})

  const refreshJobs = useCallback(async () => {
    setError(null)
    try {
      const [jobsResponse, booksResponse] = await Promise.all([listJobs(), listBooks()])
      setJobs(jobsResponse)
      setBooksCount(booksResponse.length)
      setLastRefresh(new Date())
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load jobs')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refreshJobs()
  }, [refreshJobs])

  useEffect(() => {
    const hasActiveJobs = jobs.some((job) => job.status === 'queued' || job.status === 'running')
    if (!hasActiveJobs) return

    const intervalId = window.setInterval(() => {
      void refreshJobs()
    }, 5000)

    return () => window.clearInterval(intervalId)
  }, [jobs, refreshJobs])

  const runJobAction = useCallback(async (jobId: number, action: JobActionState, request: () => Promise<Job>) => {
    setJobActions((current) => ({ ...current, [jobId]: action }))
    setError(null)
    try {
      const updatedJob = await request()
      setJobs((current) => current.map((job) => (job.id === jobId ? updatedJob : job)))
      setLastRefresh(new Date())
      void refreshJobs()
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'Failed to update job')
    } finally {
      setJobActions((current) => {
        const next = { ...current }
        delete next[jobId]
        return next
      })
    }
  }, [refreshJobs])

  const sortedJobs = useMemo(
    () =>
      [...jobs].sort((a, b) => {
        const statusOrder: Record<Job['status'], number> = {
          running: 0,
          queued: 1,
          paused: 2,
          failed: 3,
          canceled: 4,
          completed: 5,
        }
        const statusDiff = statusOrder[a.status] - statusOrder[b.status]
        if (statusDiff !== 0) return statusDiff
        const toEpoch = (value?: string | null) => (value ? new Date(value).getTime() : Number.NEGATIVE_INFINITY)
        const timestampA = toEpoch(a.completedAt) || toEpoch(a.startedAt) || toEpoch(a.createdAt)
        const timestampB = toEpoch(b.completedAt) || toEpoch(b.startedAt) || toEpoch(b.createdAt)
        return timestampB - timestampA
      }),
    [jobs]
  )

  const stats = {
    running: jobs.filter((j) => j.status === 'running').length,
    queued: jobs.filter((j) => j.status === 'queued' || j.status === 'paused').length,
    failed: jobs.filter((j) => j.status === 'failed' || j.status === 'canceled').length,
    completed: jobs.filter((j) => j.status === 'completed').length,
  }

  return (
    <AppShell
      onDataChanged={refreshJobs}
      stats={{ totalBooks: booksCount, queuedJobs: stats.running + stats.queued, failedJobs: stats.failed }}
    >
      <div className="p-6">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-foreground">Jobs</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">Monitor image generation progress</p>
          </div>

          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Clock className="h-3.5 w-3.5" />
            Last updated {lastRefresh.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
          </div>
        </div>

        <div className="mb-6 grid grid-cols-4 gap-4">
          <div className="rounded-xl border border-border bg-card p-4">
            <p className="mb-1 text-xs text-muted-foreground">Running</p>
            <p className="text-2xl font-semibold text-status-prompt-ready">{stats.running}</p>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <p className="mb-1 text-xs text-muted-foreground">Queued / Paused</p>
            <p className="text-2xl font-semibold text-status-image-queued">{stats.queued}</p>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <p className="mb-1 text-xs text-muted-foreground">Completed</p>
            <p className="text-2xl font-semibold text-status-image-ready">{stats.completed}</p>
          </div>
          <div className="rounded-xl border border-border bg-card p-4">
            <p className="mb-1 text-xs text-muted-foreground">Failed / Canceled</p>
            <p className="text-2xl font-semibold text-status-failed">{stats.failed}</p>
          </div>
        </div>

        {loading && <JobListSkeleton count={5} />}

        {!loading && !error && sortedJobs.length === 0 && (
          <EmptyState
            icon="file"
            title="No jobs yet"
            description="Jobs will appear here when you start generating images for your books."
          />
        )}

        {error && (
          <ErrorState
            message={error}
            onRetry={() => {
              setLoading(true)
              void refreshJobs()
            }}
          />
        )}

        {!loading && !error && jobs.length > 0 && (
          <>
            {sortedJobs.length > 0 ? (
              <div className="space-y-3">
                {sortedJobs.map((job) => (
                  <JobCard
                    key={job.id}
                    job={job}
                    actionState={jobActions[job.id] ?? 'idle'}
                    onPause={(currentJob) => runJobAction(currentJob.id, 'pause', () => pauseJob(currentJob.id))}
                    onResume={(currentJob) => runJobAction(currentJob.id, 'resume', () => resumeJob(currentJob.id))}
                    onCancel={(currentJob) => runJobAction(currentJob.id, 'cancel', () => cancelJob(currentJob.id))}
                  />
                ))}
              </div>
            ) : (
              <EmptyState
                icon="file"
                title="No jobs to show"
                description="Jobs will appear here when you start generating images."
              />
            )}
          </>
        )}
      </div>
    </AppShell>
  )
}

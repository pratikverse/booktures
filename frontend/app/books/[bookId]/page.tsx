'use client'

import { use, useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { AppShell } from '@/components/app-shell'
import { PageCard } from '@/components/page-card'
import { PageInspector } from '@/components/page-inspector'
import { EmptyState } from '@/components/empty-state'
import { ErrorState } from '@/components/error-state'
import { PageGridSkeleton } from '@/components/loading-skeleton'
import { StatusBadge } from '@/components/status-badge'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import {
  generateBookImages,
  generatePageImage,
  getBook,
  getJob,
  getPageAsset,
  listBookPages,
} from '@/lib/api'
import { ChevronLeft, Images, Calendar, Clock } from 'lucide-react'
import type { Book, Page, PageStatus } from '@/lib/types'

interface PageProps {
  params: Promise<{ bookId: string }>
}

function formatDate(dateString?: string | null) {
  if (!dateString) return 'Recently added'
  const date = new Date(dateString)
  return date.toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  })
}

export default function BookDetailPage({ params }: PageProps) {
  const { bookId } = use(params)
  const numericBookId = Number(bookId)
  const [book, setBook] = useState<Book | null>(null)
  const [pages, setPages] = useState<Page[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<PageStatus | 'all'>('all')
  const [selectedPage, setSelectedPage] = useState<Page | null>(null)
  const [activeJobId, setActiveJobId] = useState<number | null>(null)

  const loadBookData = useCallback(async () => {
    setError(null)

    try {
      const [bookResponse, pagesResponse] = await Promise.all([
        getBook(numericBookId),
        listBookPages(numericBookId),
      ])
      setBook(bookResponse)
      setPages(pagesResponse)
      setSelectedPage((currentPage) => {
        if (!currentPage) return null
        return pagesResponse.find((page) => page.pageNumber === currentPage.pageNumber) ?? null
      })
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load book details')
    } finally {
      setLoading(false)
    }
  }, [numericBookId])

  useEffect(() => {
    void loadBookData()
  }, [loadBookData])

  // Filter pages
  const filteredPages = useMemo(
    () => pages.filter((page) => statusFilter === 'all' || page.status === statusFilter),
    [pages, statusFilter]
  )

  // Calculate progress stats
  const stats = {
    ready: pages.filter((p) => p.status === 'image_ready').length,
    queued: pages.filter((p) => p.status === 'image_queued').length,
    prompt: pages.filter((p) => p.status === 'prompt_ready').length,
    failed: pages.filter((p) => p.status === 'failed').length,
  }

  const mergePageAsset = useCallback((pageNumber: number, asset: Awaited<ReturnType<typeof getPageAsset>>) => {
    setPages((currentPages) =>
      currentPages.map((page) =>
        page.pageNumber === pageNumber
          ? {
              ...page,
              prompt: asset.visualPrompt ?? page.prompt,
              imageUrl: asset.imageUrl ?? page.imageUrl,
              status:
                asset.imageStatus === 'generated'
                  ? 'image_ready'
                  : asset.imageStatus === 'failed'
                  ? 'failed'
                  : page.status,
              errorMessage: asset.lastError ?? undefined,
            }
          : page
      )
    )
    setSelectedPage((currentPage) =>
      currentPage?.pageNumber === pageNumber
        ? {
            ...currentPage,
            prompt: asset.visualPrompt ?? currentPage.prompt,
            imageUrl: asset.imageUrl ?? currentPage.imageUrl,
            status:
              asset.imageStatus === 'generated'
                ? 'image_ready'
                : asset.imageStatus === 'failed'
                ? 'failed'
                : currentPage.status,
            errorMessage: asset.lastError ?? undefined,
          }
        : currentPage
    )
  }, [])

  const handleGenerate = async (pageNumber: number) => {
    try {
      setPages((currentPages) =>
        currentPages.map((page) =>
          page.pageNumber === pageNumber
            ? { ...page, status: 'image_queued', errorMessage: undefined }
            : page
        )
      )
      const response = await generatePageImage(numericBookId, pageNumber)
      setActiveJobId(response.job_id)
    } catch (queueError) {
      setError(queueError instanceof Error ? queueError.message : 'Failed to queue page generation')
    }
  }

  const handleGenerateAll = async () => {
    try {
      await generateBookImages(numericBookId)
      await loadBookData()
    } catch (queueError) {
      setError(queueError instanceof Error ? queueError.message : 'Failed to queue book generation')
    }
  }

  const handleRegenerate = async (pageNumber: number) => {
    try {
      setPages((currentPages) =>
        currentPages.map((page) =>
          page.pageNumber === pageNumber
            ? { ...page, status: 'image_queued', errorMessage: undefined }
            : page
        )
      )
      const response = await generatePageImage(numericBookId, pageNumber, true)
      setActiveJobId(response.job_id)
    } catch (queueError) {
      setError(queueError instanceof Error ? queueError.message : 'Failed to requeue page generation')
    }
  }

  const handleViewMetadata = useCallback(async (pageNumber: number) => {
    try {
      const asset = await getPageAsset(numericBookId, pageNumber)
      mergePageAsset(pageNumber, asset)
    } catch (assetError) {
      setError(assetError instanceof Error ? assetError.message : 'Failed to load page asset')
    }
  }, [mergePageAsset, numericBookId])

  useEffect(() => {
    if (!activeJobId) return

    let timeoutId: ReturnType<typeof setTimeout> | undefined
    let cancelled = false

    const pollJob = async () => {
      try {
        const job = await getJob(activeJobId)
        if (cancelled) return

        if (job.pageNumber) {
          const asset = await getPageAsset(numericBookId, job.pageNumber)
          if (cancelled) return
          mergePageAsset(job.pageNumber, asset)
        }

        if (job.status === 'completed' || job.status === 'failed') {
          setActiveJobId(null)
          await loadBookData()
          return
        }
      } catch {
        // Keep polling through transient backend errors while the worker updates.
      }

      timeoutId = setTimeout(() => {
        void pollJob()
      }, 3000)
    }

    void pollJob()

    return () => {
      cancelled = true
      if (timeoutId) clearTimeout(timeoutId)
    }
  }, [activeJobId, loadBookData, mergePageAsset, numericBookId])

  const currentBook = book

  return (
    <AppShell showTopBar={false}>
      <div className="flex h-screen">
        {/* Main Content */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {/* Header */}
          <header className="border-b border-border bg-background px-6 py-4 shrink-0">
            <div className="flex items-center gap-3 mb-4">
              <Link
                href="/"
                className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
              >
                <ChevronLeft className="h-4 w-4" />
                Library
              </Link>
            </div>

            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <h1 className="text-2xl font-semibold text-foreground">
                    {currentBook?.title ?? 'Loading book...'}
                  </h1>
                  {currentBook && <StatusBadge status={currentBook.status} />}
                </div>

                <div className="flex items-center gap-4 text-sm text-muted-foreground">
                  <span className="flex items-center gap-1.5">
                    <Images className="h-4 w-4" />
                    {currentBook?.pageCount ?? 0} pages
                  </span>
                  <span className="flex items-center gap-1.5">
                    <Calendar className="h-4 w-4" />
                    {formatDate(currentBook?.createdAt)}
                  </span>
                  {activeJobId && (
                    <span className="flex items-center gap-1.5">
                      <Clock className="h-4 w-4" />
                      Polling job #{activeJobId}
                    </span>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-3">
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button disabled={!currentBook || pages.length === 0}>Generate All Images</Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Generate all images?</AlertDialogTitle>
                      <AlertDialogDescription>
                        This will generate images for all {pages.length} pages in this book.
                        This may take a while and use significant compute resources.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction onClick={handleGenerateAll}>
                        Generate All
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>
            </div>

            {/* Progress Stats */}
            <div className="flex items-center gap-4 mt-4 pt-4 border-t border-border">
              <div className="flex items-center gap-2">
                <div className="h-2 w-2 rounded-full bg-status-image-ready" />
                <span className="text-xs text-muted-foreground">
                  {stats.ready} ready
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className="h-2 w-2 rounded-full bg-status-image-queued" />
                <span className="text-xs text-muted-foreground">
                  {stats.queued} queued
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className="h-2 w-2 rounded-full bg-status-prompt-ready" />
                <span className="text-xs text-muted-foreground">
                  {stats.prompt} pending
                </span>
              </div>
              {stats.failed > 0 && (
                <div className="flex items-center gap-2">
                  <div className="h-2 w-2 rounded-full bg-status-failed" />
                  <span className="text-xs text-muted-foreground">
                    {stats.failed} failed
                  </span>
                </div>
              )}

              <div className="ml-auto">
                <Select
                  value={statusFilter}
                  onValueChange={(v) => setStatusFilter(v as PageStatus | 'all')}
                >
                  <SelectTrigger className="w-36 h-8 text-xs">
                    <SelectValue placeholder="Filter" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Pages</SelectItem>
                    <SelectItem value="image_ready">Image Ready</SelectItem>
                    <SelectItem value="image_queued">Image Queued</SelectItem>
                    <SelectItem value="prompt_ready">Prompt Ready</SelectItem>
                    <SelectItem value="failed">Failed</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </header>

          {/* Page Grid */}
          <div className="flex-1 overflow-y-auto p-6">
            {loading && <PageGridSkeleton count={12} />}

            {!loading && !error && filteredPages.length === 0 && pages.length === 0 && (
              <EmptyState
                icon="file"
                title="No pages found"
                description="This book doesn't have any pages yet. Try re-uploading the PDF."
              />
            )}

            {error && (
              <ErrorState
                message={error}
                onRetry={() => {
                  setLoading(true)
                  void loadBookData()
                }}
              />
            )}

            {!loading && !error && pages.length > 0 && (
              <>
                {filteredPages.length > 0 ? (
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-4">
                    {filteredPages.map((page) => (
                      <PageCard
                        key={page.pageNumber}
                        page={page}
                        isSelected={selectedPage?.pageNumber === page.pageNumber}
                        onSelect={setSelectedPage}
                        onGenerate={handleGenerate}
                      />
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    icon="file"
                    title="No matching pages"
                    description="Try adjusting your filter to see more pages."
                  />
                )}
              </>
            )}
          </div>
        </div>

        {/* Inspector Panel */}
        <PageInspector
          page={selectedPage}
          isLoading={loading}
          onClose={() => setSelectedPage(null)}
          onGenerate={handleGenerate}
          onRegenerate={handleRegenerate}
          onViewMetadata={handleViewMetadata}
          className="w-80 shrink-0 hidden lg:block"
        />
      </div>
    </AppShell>
  )
}

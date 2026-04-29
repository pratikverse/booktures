'use client'

import { use, useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { AppShell } from '@/components/app-shell'
import { EmptyState } from '@/components/empty-state'
import { ErrorState } from '@/components/error-state'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { StatusBadge } from '@/components/status-badge'
import {
  generatePageImage,
  getBook,
  getJob,
  getPageAsset,
  listBookPages,
  savePagePrompt,
} from '@/lib/api'
import type { Book, Page, PageAssetDetails } from '@/lib/types'
import {
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Clock,
  Image as ImageIcon,
  RefreshCw,
  RotateCcw,
  Save,
  Sparkles,
} from 'lucide-react'

interface ReaderPageProps {
  params: Promise<{ bookId: string }>
}

interface ActiveReaderJob {
  id: number
  pageNumber: number
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

function formatDateTime(dateString?: string | null) {
  if (!dateString) return 'Not generated yet'
  const date = new Date(dateString)
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function BookReaderPage({ params }: ReaderPageProps) {
  const { bookId } = use(params)
  const numericBookId = Number(bookId)

  const [book, setBook] = useState<Book | null>(null)
  const [pages, setPages] = useState<Page[]>([])
  const [selectedPageNumber, setSelectedPageNumber] = useState<number | null>(null)
  const [asset, setAsset] = useState<PageAssetDetails | null>(null)
  const [draftPrompt, setDraftPrompt] = useState('')
  const [loading, setLoading] = useState(true)
  const [assetLoading, setAssetLoading] = useState(false)
  const [savingPrompt, setSavingPrompt] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeJob, setActiveJob] = useState<ActiveReaderJob | null>(null)
  const [promptDirty, setPromptDirty] = useState(false)

  const selectedPage = useMemo(
    () => pages.find((page) => page.pageNumber === selectedPageNumber) ?? null,
    [pages, selectedPageNumber]
  )

  const loadReaderData = useCallback(async () => {
    setError(null)
    try {
      const [bookResponse, pagesResponse] = await Promise.all([
        getBook(numericBookId),
        listBookPages(numericBookId),
      ])
      setBook(bookResponse)
      setPages(pagesResponse)
      setSelectedPageNumber((current) => current ?? pagesResponse[0]?.pageNumber ?? null)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load book reader')
    } finally {
      setLoading(false)
    }
  }, [numericBookId])

  const loadAsset = useCallback(async (pageNumber: number) => {
    setAssetLoading(true)
    try {
      const assetResponse = await getPageAsset(numericBookId, pageNumber)
      setAsset(assetResponse)
      setDraftPrompt(assetResponse.promptOverride ?? assetResponse.effectivePrompt ?? assetResponse.visualPrompt ?? '')
      setPromptDirty(false)
    } catch (assetError) {
      setError(assetError instanceof Error ? assetError.message : 'Failed to load page details')
    } finally {
      setAssetLoading(false)
    }
  }, [numericBookId])

  useEffect(() => {
    void loadReaderData()
  }, [loadReaderData])

  useEffect(() => {
    if (selectedPageNumber == null) return
    void loadAsset(selectedPageNumber)
  }, [loadAsset, selectedPageNumber])

  const mergePageAsset = useCallback((pageNumber: number, assetResponse: PageAssetDetails) => {
    setPages((currentPages) =>
      currentPages.map((page) =>
        page.pageNumber === pageNumber
          ? {
              ...page,
              prompt: assetResponse.effectivePrompt ?? assetResponse.visualPrompt ?? page.prompt,
              imageUrl: assetResponse.imageUrl ?? page.imageUrl,
              status:
                assetResponse.imageStatus === 'generated'
                  ? 'image_ready'
                  : assetResponse.imageStatus === 'failed'
                    ? 'failed'
                    : page.status,
              errorMessage: assetResponse.lastError ?? undefined,
            }
          : page
      )
    )

    if (selectedPageNumber === pageNumber) {
      setAsset(assetResponse)
      setDraftPrompt((currentPrompt) =>
        promptDirty
          ? currentPrompt
          : assetResponse.promptOverride ?? assetResponse.effectivePrompt ?? assetResponse.visualPrompt ?? ''
      )
    }
  }, [promptDirty, selectedPageNumber])

  const persistPromptOverride = useCallback(async (promptText: string) => {
    if (!selectedPage) return null
    const autoPrompt = asset?.visualPrompt?.trim() ?? ''
    const nextPrompt = promptText.trim()
    const normalizedOverride = nextPrompt && nextPrompt !== autoPrompt ? nextPrompt : null
    const savedAsset = await savePagePrompt(numericBookId, selectedPage.pageNumber, normalizedOverride)
    setAsset(savedAsset)
    setDraftPrompt(savedAsset.promptOverride ?? savedAsset.effectivePrompt ?? savedAsset.visualPrompt ?? '')
    setPromptDirty(false)
    setPages((currentPages) =>
      currentPages.map((page) =>
        page.pageNumber === selectedPage.pageNumber
          ? { ...page, prompt: savedAsset.effectivePrompt ?? savedAsset.visualPrompt ?? page.prompt }
          : page
      )
    )
    return savedAsset
  }, [asset?.visualPrompt, numericBookId, selectedPage])

  const handleSavePrompt = useCallback(async () => {
    if (!selectedPage) return
    setSavingPrompt(true)
    setError(null)
    try {
      await persistPromptOverride(draftPrompt)
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Failed to save prompt override')
    } finally {
      setSavingPrompt(false)
    }
  }, [draftPrompt, persistPromptOverride, selectedPage])

  const handleResetPrompt = useCallback(async () => {
    if (!selectedPage) return
    setSavingPrompt(true)
    setError(null)
    try {
      const savedAsset = await savePagePrompt(numericBookId, selectedPage.pageNumber, null)
      setAsset(savedAsset)
      setDraftPrompt(savedAsset.effectivePrompt ?? savedAsset.visualPrompt ?? '')
      setPromptDirty(false)
      setPages((currentPages) =>
        currentPages.map((page) =>
          page.pageNumber === selectedPage.pageNumber
            ? { ...page, prompt: savedAsset.effectivePrompt ?? savedAsset.visualPrompt ?? page.prompt }
            : page
        )
      )
    } catch (resetError) {
      setError(resetError instanceof Error ? resetError.message : 'Failed to reset prompt')
    } finally {
      setSavingPrompt(false)
    }
  }, [numericBookId, selectedPage])

  const handleRegenerate = useCallback(async () => {
    if (!selectedPage) return
    setRegenerating(true)
    setError(null)
    try {
      await persistPromptOverride(draftPrompt)
      const response = await generatePageImage(numericBookId, selectedPage.pageNumber, true)
      setActiveJob({ id: response.job_id, pageNumber: selectedPage.pageNumber })
      setPages((currentPages) =>
        currentPages.map((page) =>
          page.pageNumber === selectedPage.pageNumber
            ? { ...page, status: 'image_queued', errorMessage: undefined }
            : page
        )
      )
    } catch (regenerateError) {
      setError(regenerateError instanceof Error ? regenerateError.message : 'Failed to regenerate image')
    } finally {
      setRegenerating(false)
    }
  }, [draftPrompt, numericBookId, persistPromptOverride, selectedPage])

  useEffect(() => {
    if (!activeJob) return

    let timeoutId: ReturnType<typeof setTimeout> | undefined
    let cancelled = false

    const pollJob = async () => {
      try {
        const job = await getJob(activeJob.id)
        if (cancelled) return

        const refreshedAsset = await getPageAsset(numericBookId, activeJob.pageNumber)
        if (cancelled) return
        mergePageAsset(activeJob.pageNumber, refreshedAsset)

        if (job.status === 'completed' || job.status === 'failed' || job.status === 'canceled') {
          setActiveJob(null)
          await loadReaderData()
          return
        }
      } catch {
        // keep polling through transient worker updates
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
  }, [activeJob, loadReaderData, mergePageAsset, numericBookId])

  const currentIndex = selectedPage
    ? pages.findIndex((page) => page.pageNumber === selectedPage.pageNumber)
    : -1
  const previousPage = currentIndex > 0 ? pages[currentIndex - 1] : null
  const nextPage = currentIndex >= 0 && currentIndex < pages.length - 1 ? pages[currentIndex + 1] : null

  const hasCustomPrompt = Boolean(asset?.promptOverride)
  const generatedPrompt = asset?.visualPrompt ?? ''
  const effectivePrompt = draftPrompt || asset?.effectivePrompt || generatedPrompt

  return (
    <AppShell showTopBar={false}>
      <div className="flex min-h-screen flex-col bg-background">
        <header className="shrink-0 border-b border-border bg-background px-6 py-4">
          <div className="mb-4 flex items-center gap-3">
            <Link
              href="/"
              className="flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              <ChevronLeft className="h-4 w-4" />
              Library
            </Link>
            {book && (
              <Link
                href={`/books/${book.id}`}
                className="text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                Manage Book
              </Link>
            )}
          </div>

          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="mb-2 flex items-center gap-3">
                <h1 className="text-2xl font-semibold text-foreground">
                  {book?.title ?? 'Loading reader...'}
                </h1>
                {book && <StatusBadge status={book.status} />}
              </div>
              <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
                <span className="flex items-center gap-1.5">
                  <BookOpen className="h-4 w-4" />
                  {book?.pageCount ?? 0} pages
                </span>
                <span className="flex items-center gap-1.5">
                  <Clock className="h-4 w-4" />
                  Added {formatDate(book?.createdAt)}
                </span>
                {selectedPage && <span>Reading page {selectedPage.pageNumber}</span>}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={!previousPage}
                onClick={() => previousPage && setSelectedPageNumber(previousPage.pageNumber)}
              >
                <ChevronLeft className="h-4 w-4" />
                Previous
              </Button>
              <Select
                value={selectedPageNumber ? String(selectedPageNumber) : undefined}
                onValueChange={(value) => setSelectedPageNumber(Number(value))}
              >
                <SelectTrigger className="w-36">
                  <SelectValue placeholder="Select page" />
                </SelectTrigger>
                <SelectContent>
                  {pages.map((page) => (
                    <SelectItem key={page.pageNumber} value={String(page.pageNumber)}>
                      Page {page.pageNumber}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                variant="outline"
                size="sm"
                disabled={!nextPage}
                onClick={() => nextPage && setSelectedPageNumber(nextPage.pageNumber)}
              >
                Next
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </header>

        <div className="flex-1 overflow-hidden p-6">
          {loading && (
            <div className="grid h-full gap-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(380px,0.95fr)]">
              <Skeleton className="h-full rounded-2xl" />
              <Skeleton className="h-full rounded-2xl" />
            </div>
          )}

          {!loading && error && !book && (
            <ErrorState
              message={error}
              onRetry={() => {
                setLoading(true)
                void loadReaderData()
              }}
            />
          )}

          {!loading && !error && pages.length === 0 && (
            <EmptyState
              icon="file"
              title="No pages available"
              description="This book has no extracted pages yet."
            />
          )}

          {!loading && book && selectedPage && (
            <div className="grid h-full gap-6 overflow-hidden lg:grid-cols-[minmax(0,1.05fr)_minmax(380px,0.95fr)]">
              <section className="flex min-h-0 flex-col rounded-2xl border border-border bg-card">
                <div className="border-b border-border px-5 py-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <h2 className="text-lg font-semibold text-foreground">Book Page</h2>
                      <p className="text-sm text-muted-foreground">PDF page {selectedPage.pageNumber}</p>
                    </div>
                    <StatusBadge status={selectedPage.status} />
                  </div>
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
                  {book?.pdfUrl ? (
                    <div className="h-full min-h-[480px] overflow-hidden rounded-xl border border-border bg-background">
                      <iframe
                        title={`PDF page ${selectedPage.pageNumber}`}
                        src={`${book.pdfUrl}#page=${selectedPage.pageNumber}&view=FitH`}
                        className="h-full w-full"
                      />
                    </div>
                  ) : (
                    <div className="max-w-none text-sm leading-7 text-foreground">
                      <p className="whitespace-pre-wrap">{selectedPage.textExcerpt || 'No PDF available for this book yet.'}</p>
                    </div>
                  )}
                </div>
              </section>

              <section className="flex min-h-0 flex-col rounded-2xl border border-border bg-card">
                <div className="border-b border-border px-5 py-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h2 className="text-lg font-semibold text-foreground">Illustration Workspace</h2>
                      <p className="text-sm text-muted-foreground">
                        Prompt source: {hasCustomPrompt ? 'Custom override' : 'Auto-generated'}
                      </p>
                    </div>
                    <StatusBadge status={selectedPage.status} />
                  </div>
                </div>

                <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
                  <div className="space-y-5">
                    <div className="overflow-hidden rounded-2xl border border-border bg-secondary/40">
                      <div className="flex h-[min(54vh,680px)] w-full items-center justify-center bg-secondary p-2">
                        {assetLoading ? (
                          <Skeleton className="h-full w-full rounded-none" />
                        ) : selectedPage.imageUrl ? (
                          <img
                            src={selectedPage.imageUrl}
                            alt={`Illustration for page ${selectedPage.pageNumber}`}
                            className="max-h-full w-auto max-w-full object-contain"
                          />
                        ) : (
                          <div className="flex h-full items-center justify-center">
                            <div className="text-center text-muted-foreground">
                              <ImageIcon className="mx-auto mb-3 h-12 w-12 opacity-40" />
                              <p className="text-sm">No image generated yet</p>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="grid gap-4 sm:grid-cols-2">
                      <div className="rounded-xl border border-border bg-background/60 p-4">
                        <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Summary</p>
                        <p className="text-sm leading-6 text-foreground">
                          {asset?.sceneSummary || 'No scene summary available yet for this page.'}
                        </p>
                      </div>
                      <div className="rounded-xl border border-border bg-background/60 p-4">
                        <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Prompt Used For Current Image</p>
                        <p className="whitespace-pre-wrap text-sm leading-6 text-foreground">
                          {asset?.lastUsedPrompt || effectivePrompt || 'No prompt has been used yet.'}
                        </p>
                      </div>
                    </div>

                    <div className="rounded-xl border border-border bg-background/60 p-4">
                      <div className="mb-3 flex items-center justify-between gap-3">
                        <div>
                          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Prompt Editor</p>
                          <p className="text-sm text-muted-foreground">
                            Edit the prompt for this page, save it as a custom override, then regenerate the image.
                          </p>
                        </div>
                        {hasCustomPrompt && (
                          <span className="rounded-full border border-status-image-queued/30 bg-status-image-queued/10 px-2.5 py-1 text-xs text-status-image-queued">
                            Custom prompt active
                          </span>
                        )}
                      </div>

                      <Textarea
                        value={draftPrompt}
                        onChange={(event) => {
                          setDraftPrompt(event.target.value)
                          setPromptDirty(true)
                        }}
                        className="min-h-40 resize-y bg-background"
                        placeholder="Describe the illustration for this page..."
                      />

                      <div className="mt-4 grid gap-3 sm:grid-cols-3">
                        <Button
                          variant="outline"
                          onClick={handleSavePrompt}
                          disabled={savingPrompt || regenerating || !promptDirty}
                        >
                          <Save className="h-4 w-4" />
                          Save Prompt
                        </Button>
                        <Button
                          variant="outline"
                          onClick={handleResetPrompt}
                          disabled={savingPrompt || regenerating || !hasCustomPrompt}
                        >
                          <RotateCcw className="h-4 w-4" />
                          Reset To Auto
                        </Button>
                        <Button onClick={handleRegenerate} disabled={savingPrompt || regenerating}>
                          {regenerating ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                          {selectedPage.imageUrl ? 'Regenerate Image' : 'Generate Image'}
                        </Button>
                      </div>

                      <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                        <span>Last generated: {formatDateTime(selectedPage.lastGeneratedAt)}</span>
                        {activeJob && <span>Working on job #{activeJob.id}</span>}
                        {promptDirty && <span>You have unsaved prompt changes</span>}
                      </div>
                    </div>

                    <div className="rounded-xl border border-border bg-background/60 p-4">
                      <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Auto Prompt Reference</p>
                      <p className="whitespace-pre-wrap text-sm leading-6 text-foreground">
                        {generatedPrompt || 'Auto prompt has not been generated yet.'}
                      </p>
                    </div>
                  </div>
                </div>
              </section>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  )
}

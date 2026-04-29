'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { AppShell } from '@/components/app-shell'
import { BookCard } from '@/components/book-card'
import { EmptyState } from '@/components/empty-state'
import { ErrorState } from '@/components/error-state'
import { BookCardSkeleton } from '@/components/loading-skeleton'
import { generateBookImages, listBooks, listJobs } from '@/lib/api'
import type { Book } from '@/lib/types'

export default function LibraryPage() {
  const [books, setBooks] = useState<Book[]>([])
  const [queuedJobs, setQueuedJobs] = useState(0)
  const [failedJobs, setFailedJobs] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')

  const loadLibrary = useCallback(async () => {
    setError(null)

    try {
      const [booksResponse, jobsResponse] = await Promise.all([listBooks(), listJobs()])
      setBooks(booksResponse)
      setQueuedJobs(jobsResponse.filter((job) => job.status === 'queued' || job.status === 'running').length)
      setFailedJobs(jobsResponse.filter((job) => job.status === 'failed').length)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load your library')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadLibrary()
  }, [loadLibrary])

  useEffect(() => {
    const hasProcessingBooks = books.some((book) => book.status === 'processing')
    if (!hasProcessingBooks) return

    const intervalId = window.setInterval(() => {
      void loadLibrary()
    }, 5000)

    return () => window.clearInterval(intervalId)
  }, [books, loadLibrary])

  const filteredBooks = useMemo(
    () =>
        books.filter((book) => {
          const matchesSearch = book.title.toLowerCase().includes(searchQuery.toLowerCase())
        return matchesSearch
      }),
    [books, searchQuery]
  )

  const handleGenerateAll = async (bookId: number) => {
    try {
      await generateBookImages(bookId)
      await loadLibrary()
    } catch (queueError) {
      setError(queueError instanceof Error ? queueError.message : 'Failed to queue book generation')
    }
  }

  const handleSearch = (query: string) => {
    setSearchQuery(query)
  }

  return (
    <AppShell
      onSearch={handleSearch}
      onDataChanged={loadLibrary}
      stats={{ totalBooks: books.length, queuedJobs, failedJobs }}
    >
      <div className="p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-semibold text-foreground">Library</h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              Manage your books and generate images
            </p>
          </div>

        </div>

        {/* Content */}
        {loading && (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <BookCardSkeleton key={i} />
            ))}
          </div>
        )}

        {!loading && !error && books.length === 0 && (
          <EmptyState
            icon="book"
            title="No books yet"
            description="Upload a PDF to get started with image generation."
          />
        )}

        {error && (
          <ErrorState
            message={error}
            onRetry={() => {
              setLoading(true)
              void loadLibrary()
            }}
          />
        )}

        {!loading && !error && books.length > 0 && (
          <>
            {filteredBooks.length > 0 ? (
              <div className="space-y-3">
                {filteredBooks.map((book) => (
                  <BookCard
                    key={book.id}
                    book={book}
                    onGenerateAll={handleGenerateAll}
                  />
                ))}
              </div>
            ) : (
              <EmptyState
                icon="book"
                title="No matching books"
                description="Try adjusting your search query."
              />
            )}
          </>
        )}
      </div>
    </AppShell>
  )
}

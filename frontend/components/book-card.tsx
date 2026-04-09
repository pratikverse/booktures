'use client'

import Link from 'next/link'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { StatusBadge } from '@/components/status-badge'
import { BookOpen, Images, Clock } from 'lucide-react'
import type { Book } from '@/lib/types'

interface BookCardProps {
  book: Book
  onGenerateAll?: (bookId: number) => void
  className?: string
}

function formatDate(dateString: string) {
  const date = new Date(dateString)
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function formatUpdatedAt(dateString?: string | null) {
  return dateString ? formatDate(dateString) : 'Recently updated'
}

function getProgressPercentage(book: Book) {
  if (book.pageCount === 0) return 0
  return Math.round((book.processedPages / book.pageCount) * 100)
}

export function BookCard({ book, onGenerateAll, className }: BookCardProps) {
  const progress = getProgressPercentage(book)

  return (
    <div
      className={cn(
        'group rounded-xl border border-border bg-card p-4 transition-colors hover:bg-accent/30',
        className
      )}
    >
      <div className="flex items-start gap-4">
        {/* Book Icon */}
        <div className="flex h-14 w-11 shrink-0 items-center justify-center rounded-lg bg-secondary">
          <BookOpen className="h-6 w-6 text-muted-foreground" />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2 mb-1">
            <Link
              href={`/books/${book.id}`}
              className="text-sm font-semibold text-foreground hover:underline truncate focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded"
            >
              {book.title}
            </Link>
            <StatusBadge status={book.status} />
          </div>

          <div className="flex items-center gap-3 text-xs text-muted-foreground mb-2">
            <span className="flex items-center gap-1">
              <Images className="h-3 w-3" />
              {book.processedPages}/{book.pageCount} pages
            </span>
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {formatUpdatedAt(book.updatedAt)}
            </span>
          </div>

          {/* Progress Bar */}
          {book.status === 'processing' && (
            <div className="h-1 w-full rounded-full bg-secondary overflow-hidden">
              <div
                className="h-full rounded-full bg-status-image-queued transition-all"
                style={{ width: `${progress}%` }}
              />
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          <Button asChild variant="outline" size="sm" className="text-xs">
            <Link href={`/books/${book.id}/read`}>Read</Link>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onGenerateAll?.(book.id)}
            className="text-xs"
            disabled={book.status === 'processing'}
          >
            Generate All
          </Button>
        </div>
      </div>
    </div>
  )
}

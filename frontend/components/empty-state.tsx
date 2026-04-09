'use client'

import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { BookOpen, FileText, Settings, AlertCircle } from 'lucide-react'

interface EmptyStateProps {
  icon?: 'book' | 'file' | 'settings' | 'error'
  title: string
  description: string
  action?: {
    label: string
    onClick: () => void
  }
  className?: string
}

const icons = {
  book: BookOpen,
  file: FileText,
  settings: Settings,
  error: AlertCircle,
}

export function EmptyState({ icon = 'book', title, description, action, className }: EmptyStateProps) {
  const Icon = icons[icon]

  return (
    <div className={cn('flex flex-col items-center justify-center py-16 px-4 text-center', className)}>
      <div className="rounded-full bg-secondary p-4 mb-4">
        <Icon className="h-8 w-8 text-muted-foreground" />
      </div>
      <h3 className="text-lg font-semibold text-foreground mb-1">{title}</h3>
      <p className="text-sm text-muted-foreground max-w-sm mb-6">{description}</p>
      {action && (
        <Button onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  )
}

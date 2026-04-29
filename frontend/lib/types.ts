// Book and Page Types
export type PageStatus = 'prompt_ready' | 'image_queued' | 'image_ready' | 'failed'
export type BookStatus = 'processing' | 'ready' | 'partial' | 'failed'
export type JobStatus = 'queued' | 'running' | 'paused' | 'canceled' | 'completed' | 'failed'
export type JobType = 'book_pipeline' | 'page_prompt' | 'page_image' | 'book_images'

export interface Book {
  id: number
  title: string
  pageCount: number
  processedPages: number
  status: BookStatus
  pdfUrl?: string
  createdAt?: string | null
  updatedAt?: string | null
  coverUrl?: string
}

export interface Page {
  pageNumber: number
  bookId: number
  textExcerpt: string
  prompt?: string
  imageUrl?: string
  status: PageStatus
  lastGeneratedAt?: string | null
  errorMessage?: string
}

export interface Job {
  id: number
  bookId: number
  bookTitle: string
  type: JobType
  status: JobStatus
  progress: number
  createdAt?: string | null
  startedAt?: string | null
  completedAt?: string | null
  updatedAt?: string | null
  errorMessage?: string
  pageNumber?: number
}

export interface Settings {
  ollamaUrl: string
  modelName: string
  timeout: number
  imageMode: 'quality' | 'balanced' | 'fast' | 'custom'
  imageWidth: number
  imageHeight: number
  imageSteps: number
  imageGuidance: number
  imageModel: string
}

// API Response Types
export interface ApiResponse<T> {
  data: T
  error?: string
}

export interface PaginatedResponse<T> {
  data: T[]
  total: number
  page: number
  pageSize: number
}

export interface PageAssetDetails {
  bookId: number
  pageNumber: number
  status: 'ok' | 'missing'
  sceneSummary?: string | null
  summaryShort?: string | null
  continuitySummary?: string | null
  visualPrompt?: string | null
  promptOverride?: string | null
  effectivePrompt?: string | null
  lastUsedPrompt?: string | null
  promptSource?: 'auto' | 'custom'
  negativePrompt?: string | null
  stylePreset?: string | null
  imagePath?: string | null
  imageUrl?: string | null
  imageStatus: 'pending' | 'generated' | 'failed' | string
  lastError?: string | null
}

import type { Book, Job, Page, PageAssetDetails, Settings } from './types'

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000'

type ApiBook = {
  id: number
  title: string
  page_count: number
  processed_pages: number
  status: Book['status']
  created_at?: string | null
  updated_at?: string | null
}

type ApiPage = {
  page_number: number
  book_id: number
  text_excerpt: string
  prompt?: string | null
  image_url?: string | null
  status: Page['status']
  last_generated_at?: string | null
  error_message?: string | null
}

type ApiJob = {
  id: number
  book_id: number
  book_title: string
  type: Job['type']
  status: Job['status']
  progress: number
  started_at?: string | null
  updated_at?: string | null
  error_message?: string | null
  page_number?: number | null
}

type ApiPageAsset = {
  book_id: number
  page_number: number
  status: 'ok' | 'missing'
  scene_summary?: string | null
  summary_short?: string | null
  continuity_summary?: string | null
  visual_prompt?: string | null
  prompt_override?: string | null
  effective_prompt?: string | null
  last_used_prompt?: string | null
  prompt_source?: 'auto' | 'custom'
  negative_prompt?: string | null
  style_preset?: string | null
  image_path?: string | null
  image_url?: string | null
  image_status: string
  last_error?: string | null
}

type QueueResponse = {
  status: 'queued'
  job_id: number
  book_id: number
  page_number?: number
}

type UploadResponse = {
  source: string
  filename: string
  status: string
  book_id: number
  total_pages: number | null
}

type ApiSettings = {
  ollama_url: string
  model_name: string
  timeout: number
  image_model: string
  image_width: number
  image_height: number
  image_steps: number
  image_guidance: number
}

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init)
  if (!response.ok) {
    let message = `Request failed with status ${response.status}`

    try {
      const payload = await response.json()
      if (typeof payload?.detail === 'string') {
        message = payload.detail
      }
    } catch {
      const text = await response.text()
      if (text) {
        message = text
      }
    }

    throw new Error(message)
  }

  return response.json() as Promise<T>
}

function resolveApiUrl(path?: string | null) {
  if (!path) return undefined
  if (/^https?:\/\//i.test(path)) return path
  return `${API_BASE}${path}`
}

function mapBook(book: ApiBook): Book {
  return {
    id: book.id,
    title: book.title,
    pageCount: book.page_count,
    processedPages: book.processed_pages,
    status: book.status,
    createdAt: book.created_at,
    updatedAt: book.updated_at,
  }
}

function mapPage(page: ApiPage): Page {
  return {
    pageNumber: page.page_number,
    bookId: page.book_id,
    textExcerpt: page.text_excerpt,
    prompt: page.prompt ?? undefined,
    imageUrl: resolveApiUrl(page.image_url),
    status: page.status,
    lastGeneratedAt: page.last_generated_at,
    errorMessage: page.error_message ?? undefined,
  }
}

function mapJob(job: ApiJob): Job {
  return {
    id: job.id,
    bookId: job.book_id,
    bookTitle: job.book_title,
    type: job.type,
    status: job.status,
    progress: job.progress,
    startedAt: job.started_at,
    updatedAt: job.updated_at,
    errorMessage: job.error_message ?? undefined,
    pageNumber: job.page_number ?? undefined,
  }
}

function mapPageAsset(asset: ApiPageAsset): PageAssetDetails {
  return {
    bookId: asset.book_id,
    pageNumber: asset.page_number,
    status: asset.status,
    sceneSummary: asset.scene_summary,
    summaryShort: asset.summary_short,
    continuitySummary: asset.continuity_summary,
    visualPrompt: asset.visual_prompt,
    promptOverride: asset.prompt_override,
    effectivePrompt: asset.effective_prompt,
    lastUsedPrompt: asset.last_used_prompt,
    promptSource: asset.prompt_source,
    negativePrompt: asset.negative_prompt,
    stylePreset: asset.style_preset,
    imagePath: asset.image_path,
    imageUrl: resolveApiUrl(asset.image_url),
    imageStatus: asset.image_status,
    lastError: asset.last_error,
  }
}

function mapSettings(settings: ApiSettings): Settings {
  return {
    ollamaUrl: settings.ollama_url,
    modelName: settings.model_name,
    timeout: settings.timeout,
    imageModel: settings.image_model,
    imageWidth: settings.image_width,
    imageHeight: settings.image_height,
    imageSteps: settings.image_steps,
    imageGuidance: settings.image_guidance,
  }
}

function unmapSettings(settings: Settings): ApiSettings {
  return {
    ollama_url: settings.ollamaUrl,
    model_name: settings.modelName,
    timeout: settings.timeout,
    image_model: settings.imageModel,
    image_width: settings.imageWidth,
    image_height: settings.imageHeight,
    image_steps: settings.imageSteps,
    image_guidance: settings.imageGuidance,
  }
}

export async function listBooks() {
  const books = await apiRequest<ApiBook[]>('/books')
  return books.map(mapBook)
}

export async function getBook(bookId: number) {
  const book = await apiRequest<ApiBook>(`/books/${bookId}`)
  return mapBook(book)
}

export async function listBookPages(bookId: number) {
  const pages = await apiRequest<ApiPage[]>(`/books/${bookId}/pages`)
  return pages.map(mapPage)
}

export async function listJobs() {
  const jobs = await apiRequest<ApiJob[]>('/jobs')
  return jobs.map(mapJob)
}

export async function getJob(jobId: number) {
  const job = await apiRequest<ApiJob>(`/jobs/${jobId}`)
  return mapJob(job)
}

export async function pauseJob(jobId: number) {
  const job = await apiRequest<ApiJob>(`/jobs/${jobId}/pause`, {
    method: 'POST',
  })
  return mapJob(job)
}

export async function resumeJob(jobId: number) {
  const job = await apiRequest<ApiJob>(`/jobs/${jobId}/resume`, {
    method: 'POST',
  })
  return mapJob(job)
}

export async function cancelJob(jobId: number) {
  const job = await apiRequest<ApiJob>(`/jobs/${jobId}/cancel`, {
    method: 'POST',
  })
  return mapJob(job)
}

export async function uploadPdf(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  return apiRequest<UploadResponse>('/upload-pdf', {
    method: 'POST',
    body: formData,
  })
}

export async function generatePageImage(bookId: number, pageNumber: number, forceRegenerate = false) {
  return apiRequest<QueueResponse>(`/books/${bookId}/pages/${pageNumber}/generate-image`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ force_regenerate: forceRegenerate }),
  })
}

export async function generateBookImages(bookId: number) {
  return apiRequest<QueueResponse>(`/books/${bookId}/generate-images`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  })
}

export async function getPageAsset(bookId: number, pageNumber: number) {
  const asset = await apiRequest<ApiPageAsset>(`/books/${bookId}/pages/${pageNumber}/asset`)
  return mapPageAsset(asset)
}

export async function savePagePrompt(bookId: number, pageNumber: number, promptOverride: string | null) {
  const asset = await apiRequest<ApiPageAsset>(`/books/${bookId}/pages/${pageNumber}/prompt`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt_override: promptOverride }),
  })
  return mapPageAsset(asset)
}

export async function getSettings() {
  const settings = await apiRequest<ApiSettings>('/settings')
  return mapSettings(settings)
}

export async function saveSettings(settings: Settings) {
  const saved = await apiRequest<ApiSettings>('/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(unmapSettings(settings)),
  })
  return mapSettings(saved)
}

import type { Book, Page, Job, Settings } from './types'

export const mockBooks: Book[] = [
  {
    id: 1,
    title: 'The Great Gatsby',
    pageCount: 180,
    processedPages: 180,
    status: 'ready',
    createdAt: '2025-03-15T10:30:00Z',
    updatedAt: '2025-03-15T14:45:00Z',
  },
  {
    id: 2,
    title: '1984',
    pageCount: 328,
    processedPages: 156,
    status: 'processing',
    createdAt: '2025-03-18T09:00:00Z',
    updatedAt: '2025-03-20T11:30:00Z',
  },
  {
    id: 3,
    title: 'Pride and Prejudice',
    pageCount: 432,
    processedPages: 432,
    status: 'ready',
    createdAt: '2025-03-10T14:00:00Z',
    updatedAt: '2025-03-12T16:20:00Z',
  },
  {
    id: 4,
    title: 'The Catcher in the Rye',
    pageCount: 234,
    processedPages: 12,
    status: 'partial',
    createdAt: '2025-03-19T08:15:00Z',
    updatedAt: '2025-03-19T08:45:00Z',
  },
  {
    id: 5,
    title: 'To Kill a Mockingbird',
    pageCount: 281,
    processedPages: 0,
    status: 'failed',
    createdAt: '2025-03-17T12:00:00Z',
    updatedAt: '2025-03-17T12:05:00Z',
  },
]

export const mockPages: Page[] = [
  {
    pageNumber: 1,
    bookId: 1,
    textExcerpt: 'In my younger and more vulnerable years my father gave me some advice that I have been turning over in my mind ever since...',
    prompt: 'A young man in 1920s attire standing on a veranda, contemplative expression, golden hour lighting, art deco architecture in the background',
    imageUrl: '/placeholder-image.jpg',
    status: 'image_ready',
    lastGeneratedAt: '2025-03-15T14:30:00Z',
  },
  {
    pageNumber: 2,
    bookId: 1,
    textExcerpt: 'Whenever you feel like criticizing anyone, he told me, just remember that all the people in this world have not had the advantages that you have had...',
    prompt: 'A father and son conversation in a luxurious study, warm amber lighting, leather chairs, books on shelves',
    status: 'image_queued',
    lastGeneratedAt: '2025-03-15T14:32:00Z',
  },
  {
    pageNumber: 3,
    bookId: 1,
    textExcerpt: 'He did not say any more, but we have always been unusually communicative in a reserved way, and I understood that he meant a great deal more than that...',
    prompt: 'Two figures in silhouette against a window, dusk lighting, elegant room interior',
    status: 'prompt_ready',
  },
  {
    pageNumber: 4,
    bookId: 1,
    textExcerpt: 'And, after boasting this way of my tolerance, I come to the admission that it has a limit...',
    status: 'failed',
    errorMessage: 'Image generation timed out after 120 seconds',
    lastGeneratedAt: '2025-03-15T14:35:00Z',
  },
  {
    pageNumber: 5,
    bookId: 1,
    textExcerpt: 'Conduct may be founded on the hard rock or the wet marshes, but after a certain point I do not care what it is founded on...',
    prompt: 'A metaphorical landscape showing contrasting terrain - solid rock meeting marshland, dramatic lighting',
    imageUrl: '/placeholder-image.jpg',
    status: 'image_ready',
    lastGeneratedAt: '2025-03-15T14:40:00Z',
  },
]

// Generate more pages for testing
for (let i = 6; i <= 20; i++) {
  const statuses: Page['status'][] = ['prompt_ready', 'image_queued', 'image_ready', 'failed']
  const randomStatus = statuses[Math.floor(Math.random() * statuses.length)]
  
  mockPages.push({
    pageNumber: i,
    bookId: 1,
    textExcerpt: `Sample text excerpt for page ${i}. This represents the extracted text content from the PDF...`,
    prompt: randomStatus !== 'failed' ? `Generated prompt for page ${i} scene description...` : undefined,
    imageUrl: randomStatus === 'image_ready' ? '/placeholder-image.jpg' : undefined,
    status: randomStatus,
    lastGeneratedAt: randomStatus !== 'prompt_ready' ? new Date(Date.now() - Math.random() * 86400000).toISOString() : undefined,
    errorMessage: randomStatus === 'failed' ? 'Generation failed: Model timeout' : undefined,
  })
}

export const mockJobs: Job[] = [
  {
    id: 1,
    bookId: 2,
    bookTitle: '1984',
    type: 'full_book',
    status: 'running',
    progress: 47,
    startedAt: '2025-03-20T10:00:00Z',
    updatedAt: '2025-03-20T11:30:00Z',
  },
  {
    id: 2,
    bookId: 1,
    bookTitle: 'The Great Gatsby',
    type: 'single_page',
    status: 'queued',
    progress: 0,
    startedAt: '2025-03-20T11:35:00Z',
    updatedAt: '2025-03-20T11:35:00Z',
    pageNumber: 4,
  },
  {
    id: 3,
    bookId: 3,
    bookTitle: 'Pride and Prejudice',
    type: 'full_book',
    status: 'completed',
    progress: 100,
    startedAt: '2025-03-12T14:00:00Z',
    updatedAt: '2025-03-12T16:20:00Z',
  },
  {
    id: 4,
    bookId: 5,
    bookTitle: 'To Kill a Mockingbird',
    type: 'full_book',
    status: 'failed',
    progress: 0,
    startedAt: '2025-03-17T12:00:00Z',
    updatedAt: '2025-03-17T12:05:00Z',
    errorMessage: 'Failed to connect to Ollama server at localhost:11434',
  },
  {
    id: 5,
    bookId: 4,
    bookTitle: 'The Catcher in the Rye',
    type: 'single_page',
    status: 'running',
    progress: 68,
    startedAt: '2025-03-19T08:30:00Z',
    updatedAt: '2025-03-19T08:45:00Z',
    pageNumber: 13,
  },
]

export const mockSettings: Settings = {
  ollamaUrl: 'http://localhost:11434',
  modelName: 'llama3.2',
  timeout: 120,
  imageWidth: 1024,
  imageHeight: 1024,
  imageSteps: 30,
  imageGuidance: 7.5,
  imageModel: 'stable-diffusion-xl',
}

// Stats for quick overview
export const mockStats = {
  totalBooks: mockBooks.length,
  queuedJobs: mockJobs.filter(j => j.status === 'queued' || j.status === 'running').length,
  failedJobs: mockJobs.filter(j => j.status === 'failed').length,
}

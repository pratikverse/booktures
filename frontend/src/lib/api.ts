import { toast } from "sonner";
import { uploadPdf } from "@/services/books";

export * from "@/services/types";
export { fileUrl } from "@/services/images";
export {
  getBooks,
  getBook,
  getBookContent,
  uploadPdf,
  generateBookImages,
  deleteBook,
} from "@/services/books";
export { getJobs, manageJobAction } from "@/services/jobs";
export { getSettings, getOllamaModels, saveSettings } from "@/services/settings";
export { getBookCharacters } from "@/services/characters";
export { getHealth } from "@/services/health";
export { apiClient, normalizeApiError } from "@/services/apiClient";

export async function uploadFile(file: File, onProgress?: (progress: number) => void) {
  return uploadPdf(file, onProgress);
}

export function notifyError(e: unknown, fallback = "Something went wrong") {
  const msg = e instanceof Error ? e.message : fallback;
  toast.error(msg);
}

import { apiClient } from "./apiClient";
import type { Book, BookContent } from "./types";

export async function getBooks(): Promise<Book[]> {
  const { data } = await apiClient.get<Book[]>("/books");
  return data.map((b) => ({ ...b, progress: Math.round((b.progress ?? 0) * 100) }));
}

export async function getBook(id: number): Promise<Book> {
  const { data } = await apiClient.get<Book>(`/books/${id}`);
  return data;
}

export async function getBookContent(id: number): Promise<BookContent> {
  const { data } = await apiClient.get<BookContent>(`/books/${id}/content`);
  return data;
}

export async function uploadPdf(
  file: File,
  onUploadProgress?: (percent: number) => void
): Promise<{ id: number; title: string; status: string; message: string }> {
  const fd = new FormData();
  fd.append("file", file);

  const { data } = await apiClient.post("/upload-pdf", fd, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (event) => {
      if (!onUploadProgress) return;
      const total = event.total ?? 1;
      onUploadProgress(Math.round((event.loaded * 100) / total));
    },
  });

  return data;
}

export async function generateBookImages(id: number): Promise<{ message: string }> {
  const { data } = await apiClient.post(`/books/${id}/generate-images`, {});
  return data;
}

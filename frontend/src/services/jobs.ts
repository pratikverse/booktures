import { apiClient } from "./apiClient";
import type { Job } from "./types";

export async function getJobs(): Promise<Job[]> {
  const { data } = await apiClient.get<any[]>("/jobs");
  return data.map((j) => ({
    id: j.id,
    book_id: j.book_id,
    bookTitle: j.book_title,
    type: j.type,
    label: j.label,
    status: j.status,
    note: j.note,
    createdAt: j.created_at,
    progress: Math.round((j.progress ?? 0) * 100),
  }));
}

export async function manageJobAction(
  id: number,
  action: "pause" | "resume" | "cancel" | "retry"
): Promise<{ message: string }> {
  const { data } = await apiClient.post(`/jobs/${id}/action`, { action });
  return data;
}

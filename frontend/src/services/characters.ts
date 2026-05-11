import { apiClient } from "./apiClient";
import type { Character } from "./types";

export async function getBookCharacters(bookId: number): Promise<Character[]> {
  const { data } = await apiClient.get<Character[]>(`/books/${bookId}/characters`);
  return data;
}

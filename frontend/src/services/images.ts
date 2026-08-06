import { apiClient } from "./apiClient";

export function fileUrl(relPath: string) {
  if (!relPath) return "";
  if (/^https?:\/\//i.test(relPath)) return relPath;
  const clean = relPath.startsWith("/") ? relPath : `/${relPath}`;
  return `${apiClient.defaults.baseURL}${clean}`;
}

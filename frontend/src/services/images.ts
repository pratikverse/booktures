import { apiClient } from "./apiClient";

export function fileUrl(relPath: string) {
  if (!relPath) return "";
  const clean = relPath.startsWith("/") ? relPath : `/${relPath}`;
  return `${apiClient.defaults.baseURL}${clean}`;
}

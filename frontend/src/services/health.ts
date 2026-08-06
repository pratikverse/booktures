import { apiClient } from "./apiClient";

export interface HealthStatus {
  status: string;
}

export async function getHealth(): Promise<HealthStatus> {
  // /ready, not /health: something in front of Render (likely Cloudflare)
  // blocks requests to a path literally named "/health" outright (no
  // response at all), while /ready - which also confirms DB connectivity -
  // works reliably. Normalize its "ready" status to "ok" for the badge.
  const { data } = await apiClient.get<{ status: string }>("/ready");
  return { status: data.status === "ready" ? "ok" : data.status };
}

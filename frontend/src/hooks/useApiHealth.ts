import { useEffect, useState } from "react";
import { getHealth, type HealthStatus } from "@/lib/api";

// Longer than Drape's original 15s: polling this fast against Render's
// free tier (fronted by Cloudflare) was tripping rate-based protection on
// the /health path specifically, returning 503s the app was otherwise
// never seeing on /settings or /books.
const POLL_INTERVAL_MS = 60_000;

export function useApiHealth() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        const result = await getHealth();
        if (!cancelled) {
          setHealth(result);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err as Error);
          setHealth(null);
        }
      }
    }

    check();
    const interval = setInterval(check, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  return { health, error };
}

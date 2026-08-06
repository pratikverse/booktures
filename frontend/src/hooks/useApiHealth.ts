import { useEffect, useState } from "react";
import { getHealth, type HealthStatus } from "@/lib/api";

const POLL_INTERVAL_MS = 15_000;

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

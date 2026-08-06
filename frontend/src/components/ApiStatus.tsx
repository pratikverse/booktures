import { useApiHealth } from "@/hooks/useApiHealth";

const STATUS_STYLES: Record<string, { label: string; dot: string }> = {
  loading: { label: "connecting…", dot: "bg-muted-foreground" },
  ok: { label: "live api", dot: "bg-success" },
  offline: { label: "offline", dot: "bg-destructive" },
};

export default function ApiStatus() {
  const { health, error } = useApiHealth();

  let statusKey = "loading";
  if (error) {
    statusKey = "offline";
  } else if (health) {
    statusKey = health.status === "ok" ? "ok" : health.status;
  }

  const { label, dot } = STATUS_STYLES[statusKey] ?? { label: statusKey, dot: "bg-warning" };

  return (
    <span
      title={error?.message}
      className="hidden shrink-0 items-center gap-1.5 rounded-sm border border-border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-widest text-muted-foreground sm:inline-flex"
    >
      <span className={`size-1.5 rounded-full ${dot}`} aria-hidden="true" />
      {label}
    </span>
  );
}

import type { ReactNode } from "react";

export default function PageHeader({
  kicker,
  title,
  subtitle,
  action,
}: {
  kicker: string;
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.25em] text-primary">{kicker}</p>
        <h1 className="mt-2 font-display text-2xl font-bold leading-tight sm:text-3xl">{title}</h1>
        {subtitle && <p className="mt-1 text-muted-foreground">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

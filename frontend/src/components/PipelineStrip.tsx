import { Reveal } from "@/lib/reveal";

const STEPS = [
  { label: "Upload", note: "PDF ingest" },
  { label: "Extract", note: "text & pages" },
  { label: "Characters", note: "visual profiles" },
  { label: "Prompts", note: "scene & style" },
  { label: "Illustrate", note: "AI generated art" },
];

export default function PipelineStrip() {
  return (
    <ol className="grid gap-3 sm:grid-cols-5">
      {STEPS.map((s, i) => (
        <Reveal key={s.label} as="li" delay={i * 70}>
          <div className="h-full rounded-2xl border border-border bg-card p-4 transition-all duration-300 hover:-translate-y-1 hover:border-primary/40 hover:shadow-md">
            <span className="num font-mono text-[10px] text-primary">
              {String(i + 1).padStart(2, "0")}
            </span>
            <p className="mt-1 font-display text-sm font-semibold text-foreground">{s.label}</p>
            <p className="text-xs text-muted-foreground">{s.note}</p>
          </div>
        </Reveal>
      ))}
    </ol>
  );
}

const STEPS = [
  { label: "Upload", note: "PDF ingest" },
  { label: "Extract", note: "text & pages" },
  { label: "Characters", note: "visual profiles" },
  { label: "Prompts", note: "scene & style" },
  { label: "Illustrate", note: "AI generated art" },
];

export default function PipelineStrip() {
  return (
    <ol className="grid gap-2 sm:grid-cols-5">
      {STEPS.map((s, i) => (
        <li
          key={s.label}
          className="rise rounded-md border border-border bg-card p-3"
          style={{ animationDelay: `${i * 70}ms` }}
        >
          <span className="num font-mono text-[10px] text-primary">
            {String(i + 1).padStart(2, "0")}
          </span>
          <p className="mt-1 font-display text-sm font-semibold">{s.label}</p>
          <p className="text-xs text-muted-foreground">{s.note}</p>
        </li>
      ))}
    </ol>
  );
}

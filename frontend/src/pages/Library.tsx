import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getBooks, uploadPdf } from "@/lib/api";
import { Loader2, Search, Upload } from "lucide-react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import BookCard from "@/components/BookCard";
import PipelineStrip from "@/components/PipelineStrip";
import { Reveal } from "@/lib/reveal";

export default function Library() {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [search, setSearch] = useState("");

  const { data: books = [], isLoading } = useQuery({
    queryKey: ["books"],
    queryFn: getBooks,
    refetchInterval: (q) => {
      const data = q.state.data as any[] | undefined;
      return data?.some(
        (b) => b.status === "queued" || b.status === "processing" || b.status === "generating_images"
      )
        ? 5000
        : false;
    },
  });

  const filtered = books.filter((b) =>
    search ? b.title.toLowerCase().includes(search.toLowerCase()) : true
  );

  const handleUpload = async (file: File) => {
    const allowed = ["application/pdf", "image/png", "image/jpeg"];
    if (!allowed.includes(file.type)) {
      toast.error("Please upload a PDF or JPG/PNG image.");
      return;
    }
    setUploading(true);
    setUploadProgress(0);
    try {
      const res = await uploadPdf(file, setUploadProgress);
      toast.success(`Uploaded "${res.title}"`);
      qc.invalidateQueries({ queryKey: ["books"] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    } catch (e) {
      toast.error((e as { message?: string })?.message ?? "Upload failed");
    } finally {
      setUploading(false);
      setUploadProgress(0);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <div className="relative overflow-hidden">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 -z-10"
        style={{
          background:
            "radial-gradient(60rem 40rem at 50% -10%, color-mix(in oklab, hsl(var(--primary)) 12%, transparent), transparent 60%)",
        }}
      />

      <section className="relative mx-auto max-w-5xl px-6 pt-20 pb-16 sm:pt-24 sm:pb-20">
        <Reveal delay={0}>
          <p className="inline-flex items-center gap-2 rounded-full border border-border bg-card/60 px-3 py-1 text-xs font-medium text-muted-foreground backdrop-blur">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-60" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-primary" />
            </span>
            AI illustrated reading · local + cloud pipeline
          </p>
        </Reveal>

        <Reveal delay={80}>
          <h1 className="mt-6 max-w-3xl text-4xl font-bold leading-[1.05] tracking-tight text-foreground sm:text-5xl">
            Books can&apos;t picture themselves.
          </h1>
        </Reveal>

        <Reveal delay={160}>
          <p className="mt-6 max-w-2xl text-lg leading-relaxed text-muted-foreground">
            Upload a PDF and Booktures reads it page by page — pulling out the narrative, tracking
            characters across chapters, and generating consistent illustrations for the scenes as
            they happen.
          </p>
        </Reveal>

        <Reveal delay={240}>
          <div className="mt-9 flex items-center gap-3">
            <input
              ref={fileRef}
              type="file"
              accept="application/pdf,image/*"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleUpload(f);
              }}
            />
            <Button onClick={() => fileRef.current?.click()} disabled={uploading} className="gap-2">
              <Upload className="size-4" />
              {uploading ? `Uploading ${uploadProgress}%` : "Upload a PDF"}
            </Button>
          </div>
        </Reveal>

        <div className="mt-16">
          <PipelineStrip />
        </div>
      </section>

      <section className="relative mx-auto max-w-7xl px-6 pb-16">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4 border-t border-border pt-8">
          <div className="relative w-full max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search books..."
              className="pl-9"
            />
          </div>
          <div className="text-sm text-muted-foreground">
            <span className="font-semibold text-foreground">{books.length}</span> books
          </div>
        </div>

        {isLoading ? (
          <div className="grid place-items-center py-20 text-muted-foreground">
            <Loader2 className="size-6 animate-spin" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-border p-16 text-center">
            <h3 className="text-lg font-semibold text-foreground">No books yet</h3>
            <p className="mt-1 text-muted-foreground">Upload a PDF above to get started.</p>
          </div>
        ) : (
          <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {filtered.map((b) => (
              <BookCard key={b.id} book={b} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

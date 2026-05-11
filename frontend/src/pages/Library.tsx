import { useQuery } from "@tanstack/react-query";
import { getBooks } from "@/lib/api";
import BookCard from "@/components/BookCard";
import { useOutletContext } from "react-router-dom";
import { Loader2 } from "lucide-react";

export default function Library() {
  const ctx = useOutletContext<{ search: string }>();
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
    ctx?.search ? b.title.toLowerCase().includes(ctx.search.toLowerCase()) : true
  );

  return (
    <div className="p-6 md:p-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight">Your Library</h1>
        <p className="text-muted-foreground mt-1">
          Upload a PDF to bring it to life with AI-generated illustrations.
        </p>
      </div>

      {isLoading ? (
        <div className="grid place-items-center py-20 text-muted-foreground">
          <Loader2 className="size-6 animate-spin" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="border-2 border-dashed border-border rounded-xl p-16 text-center">
          <h3 className="font-semibold text-lg">No books yet</h3>
          <p className="text-muted-foreground mt-1">
            Click "Upload PDF" in the top bar to get started.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filtered.map((b) => (
            <BookCard key={b.id} book={b} />
          ))}
        </div>
      )}
    </div>
  );
}

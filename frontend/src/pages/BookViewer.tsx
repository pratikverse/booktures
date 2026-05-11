import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { fileUrl, getBook, getBookCharacters, getBookContent } from "@/lib/api";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ChevronLeft, ChevronRight, ArrowLeft, ImageOff, Loader2 } from "lucide-react";

export default function BookViewer() {
  const { bookId } = useParams<{ bookId: string }>();
  const id = Number(bookId);
  const [pageNum, setPageNum] = useState(1);

  const { data: book } = useQuery({ queryKey: ["book", id], queryFn: () => getBook(id) });
  const { data: content, isLoading } = useQuery({
    queryKey: ["book-content", id],
    queryFn: () => getBookContent(id),
  });
  const { data: characters = [] } = useQuery({
    queryKey: ["book-characters", id],
    queryFn: () => getBookCharacters(id),
  });

  const total = content?.total_pages ?? 0;
  const currentPage = useMemo(
    () => content?.pages.find((p) => p.page === pageNum) ?? content?.pages[0],
    [content, pageNum]
  );
  const pageCharacters = useMemo(() => {
    if (!currentPage?.characters) return [];
    const raw = currentPage.characters.toLowerCase();
    return characters.filter((c) => raw.includes(c.name.toLowerCase()));
  }, [characters, currentPage]);

  const pdfUrl = book?.file_path ? fileUrl(book.file_path) : "";
  const imageSrc = currentPage?.illustration_url
    ? `${fileUrl(currentPage.illustration_url)}?v=${encodeURIComponent(
        `${currentPage.page}-${currentPage.image_prompt ?? ""}-${currentPage.summary ?? ""}`
      )}`
    : "";

  const go = (delta: number) => {
    const next = Math.max(1, Math.min(total || 1, pageNum + delta));
    setPageNum(next);
  };

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col">
      <div className="border-b bg-card px-4 md:px-6 py-3 flex items-center gap-3">
        <Button asChild variant="ghost" size="sm">
          <Link to="/"><ArrowLeft className="size-4" /> Library</Link>
        </Button>
        <h1 className="font-semibold truncate flex-1">{book?.title ?? "Loading..."}</h1>
        <Button variant="outline" size="icon" onClick={() => go(-1)} disabled={pageNum <= 1}>
          <ChevronLeft className="size-4" />
        </Button>
        <Select value={String(pageNum)} onValueChange={(v) => setPageNum(Number(v))}>
          <SelectTrigger className="w-28"><SelectValue /></SelectTrigger>
          <SelectContent className="max-h-72">
            {Array.from({ length: total }, (_, i) => i + 1).map((p) => (
              <SelectItem key={p} value={String(p)}>Page {p}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-sm text-muted-foreground whitespace-nowrap">
          {pageNum} / {total || "-"}
        </span>
        <Button variant="outline" size="icon" onClick={() => go(1)} disabled={pageNum >= total}>
          <ChevronRight className="size-4" />
        </Button>
      </div>

      <div className="flex-1 grid lg:grid-cols-2 min-h-0">
        <div className="bg-muted border-r min-h-0">
          {pdfUrl ? (
            <iframe key={pageNum} title="PDF" src={`${pdfUrl}#page=${pageNum}`} className="w-full h-full" />
          ) : (
            <div className="grid place-items-center h-full text-muted-foreground">
              <Loader2 className="size-6 animate-spin" />
            </div>
          )}
        </div>

        <div className="overflow-auto p-6 space-y-4 bg-background">
          {isLoading ? (
            <Loader2 className="size-6 animate-spin text-muted-foreground" />
          ) : !currentPage ? (
            <p className="text-muted-foreground">No content for this page yet.</p>
          ) : (
            <>
              <Card className="overflow-hidden shadow-card aspect-[4/3] bg-muted grid place-items-center">
                {currentPage.illustration_url ? (
                  <img
                    src={imageSrc}
                    alt={`Illustration for page ${currentPage.page}`}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="text-muted-foreground flex flex-col items-center gap-2">
                    <ImageOff className="size-8" />
                    <span className="text-sm">No illustration yet</span>
                  </div>
                )}
              </Card>

              <Card className="p-4 shadow-card">
                <h3 className="font-semibold mb-1">Narrative Summary</h3>
                <p className="text-sm text-muted-foreground whitespace-pre-wrap">{currentPage.summary || "-"}</p>
              </Card>
              <Card className="p-4 shadow-card">
                <h3 className="font-semibold mb-1">Characters</h3>
                <p className="text-sm text-muted-foreground whitespace-pre-wrap">{currentPage.characters || "-"}</p>
                {pageCharacters.length > 0 && (
                  <div className="mt-3 space-y-2">
                    {pageCharacters.map((c) => (
                      <div key={c.id} className="rounded-md border p-2">
                        <div className="text-sm font-medium">{c.name}</div>
                        <div className="text-xs text-muted-foreground">{c.visual_profile}</div>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
              <Card className="p-4 shadow-card">
                <h3 className="font-semibold mb-1">Scene Setting</h3>
                <p className="text-sm text-muted-foreground whitespace-pre-wrap">{currentPage.scenes || "-"}</p>
              </Card>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

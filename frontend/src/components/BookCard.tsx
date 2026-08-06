import { Book, deleteBook, generateBookImages } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { BookOpen, Sparkles, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

const statusVariant: Record<string, string> = {
  queued: "bg-muted text-muted-foreground",
  uploaded: "bg-muted text-muted-foreground",
  processing: "bg-warning/20 text-warning-foreground border border-warning/40",
  analyzed: "bg-accent/20 text-accent border border-accent/40",
  generating_images: "bg-primary/20 text-primary border border-primary/40",
  completed: "bg-success/20 text-success border border-success/40",
  ready: "bg-success/20 text-success border border-success/40",
  failed: "bg-destructive/20 text-destructive border border-destructive/40",
};

const labels: Record<string, string> = {
  queued: "Queued",
  uploaded: "Uploaded",
  processing: "Analyzing",
  analyzed: "Analyzed",
  generating_images: "Generating Images",
  completed: "Completed",
  ready: "Ready",
  failed: "Failed",
};

export default function BookCard({ book }: { book: Book }) {
  const qc = useQueryClient();
  const showProgress =
    book.status === "queued" || book.status === "processing" || book.status === "generating_images";

  const genMut = useMutation({
    mutationFn: () => generateBookImages(book.id),
    onSuccess: (r) => {
      toast.success(r.message || "Image generation queued");
      qc.invalidateQueries({ queryKey: ["books"] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e) => toast.error((e as { message?: string })?.message ?? "Failed"),
  });

  const deleteMut = useMutation({
    mutationFn: () => deleteBook(book.id),
    onSuccess: () => {
      toast.success(`Deleted "${book.title}"`);
      qc.invalidateQueries({ queryKey: ["books"] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e) => toast.error((e as { message?: string })?.message ?? "Delete failed"),
  });

  return (
    <Card className="p-5 shadow-card hover:shadow-elegant transition-shadow flex flex-col gap-4">
      <div className="flex items-start gap-3">
        <div className="size-12 rounded-lg bg-gradient-primary grid place-items-center shrink-0">
          <BookOpen className="size-6 text-primary-foreground" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold leading-tight truncate" title={book.title}>
            {book.title}
          </h3>
          <Badge className={`mt-1 ${statusVariant[book.status] ?? ""}`} variant="outline">
            {labels[book.status] ?? book.status}
          </Badge>
        </div>
      </div>

      {showProgress && (
        <div className="space-y-1">
          <Progress value={book.progress} />
          <div className="text-xs text-muted-foreground text-right">{book.progress}%</div>
        </div>
      )}

      <div className="flex gap-2 mt-auto">
        <Button asChild variant="outline" className="flex-1">
          <Link to={`/books/${book.id}`}>Read</Link>
        </Button>
        {book.status === "analyzed" && (
          <Button
            className="flex-1 bg-gradient-primary gap-1"
            disabled={genMut.isPending}
            onClick={() => genMut.mutate()}
          >
            <Sparkles className="size-4" />
            {genMut.isPending ? "..." : "Generate"}
          </Button>
        )}
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="outline" size="icon" disabled={deleteMut.isPending} aria-label="Delete book">
              <Trash2 className="size-4" />
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete "{book.title}"?</AlertDialogTitle>
              <AlertDialogDescription>
                This permanently removes the book, its extracted pages, characters, and generated
                illustrations. This can't be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={() => deleteMut.mutate()}>Delete</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </Card>
  );
}

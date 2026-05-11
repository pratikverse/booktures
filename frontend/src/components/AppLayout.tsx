import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { BookOpen, ListTodo, Settings as SettingsIcon, Search, Upload } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getBooks, uploadPdf } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

const navItems = [
  { to: "/", label: "Library", icon: BookOpen, end: true },
  { to: "/jobs", label: "Jobs", icon: ListTodo },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

export function SearchContext() {}

export default function AppLayout() {
  const { data: books = [] } = useQuery({ queryKey: ["books"], queryFn: getBooks });
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [search, setSearch] = useState("");
  const navigate = useNavigate();

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
    <div className="min-h-screen bg-background flex">
      <aside className="w-60 shrink-0 border-r border-sidebar-border bg-sidebar hidden md:flex flex-col">
        <Link to="/" className="px-6 py-5 flex items-center gap-2">
          <div className="size-9 rounded-lg bg-gradient-primary shadow-elegant grid place-items-center">
            <BookOpen className="size-5 text-primary-foreground" />
          </div>
          <div>
            <div className="font-semibold text-sidebar-foreground leading-tight">Booktures</div>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">v 2.0</div>
          </div>
        </Link>
        <nav className="px-3 py-2 flex flex-col gap-1">
          {navItems.map((it) => (
            <NavLink
              key={it.to}
              to={it.to}
              end={it.end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                  isActive
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60"
                )
              }
            >
              <it.icon className="size-4" />
              {it.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-16 border-b bg-card/70 backdrop-blur sticky top-0 z-10 flex items-center gap-4 px-4 md:px-6">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              navigate(`/?q=${encodeURIComponent(search)}`);
            }}
            className="relative flex-1 max-w-md"
          >
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search books..."
              className="pl-9"
            />
          </form>
          <div className="text-sm text-muted-foreground hidden sm:block">
            <span className="font-semibold text-foreground">{books.length}</span> books
          </div>
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
          <Button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="gap-2 bg-gradient-primary hover:opacity-95"
          >
            <Upload className="size-4" />
            {uploading ? `Uploading ${uploadProgress}%` : "Upload PDF"}
          </Button>
        </header>
        <main className="flex-1 overflow-auto">
          <Outlet context={{ search }} />
        </main>
      </div>
    </div>
  );
}

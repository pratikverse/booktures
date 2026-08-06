import { NavLink, Outlet } from "react-router-dom";
import { BookOpen, ListTodo, Settings as SettingsIcon, HelpCircle } from "lucide-react";
import ApiStatus from "@/components/ApiStatus";
import { cn } from "@/lib/utils";

const navItems = [
  { to: "/", label: "Library", icon: BookOpen, end: true },
  { to: "/jobs", label: "Jobs", icon: ListTodo },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
  { to: "/how-it-works", label: "How it works", icon: HelpCircle },
];

export default function AppLayout() {
  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-40 border-b border-border/70 bg-background/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-3">
          <NavLink to="/" className="flex min-w-0 items-center gap-2.5">
            <span className="grid size-8 shrink-0 place-items-center rounded-sm bg-gradient-primary text-primary-foreground">
              <BookOpen className="size-4" />
            </span>
            <span className="truncate font-display text-base font-semibold tracking-tight">
              Booktures
            </span>
            <ApiStatus />
          </NavLink>
          <nav className="flex items-center gap-1 text-sm">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-1.5 rounded-sm px-2.5 py-1.5 transition-colors",
                    isActive
                      ? "bg-secondary text-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  )
                }
              >
                <item.icon className="size-3.5" />
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  );
}

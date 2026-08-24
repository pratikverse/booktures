import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { BookOpen, HelpCircle, ListTodo, Menu, Settings as SettingsIcon, X } from "lucide-react";
import ApiStatus from "@/components/ApiStatus";
import { cn } from "@/lib/utils";

const navItems = [
  { to: "/", label: "Library", icon: BookOpen, end: true },
  { to: "/jobs", label: "Jobs", icon: ListTodo },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
  { to: "/how-it-works", label: "How it works", icon: HelpCircle },
];

export default function AppLayout() {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div className="min-h-screen bg-background">
      <header
        className={cn(
          "sticky top-0 z-50 transition-colors duration-300",
          scrolled
            ? "border-b border-border bg-background/85 backdrop-blur-md"
            : "border-b border-transparent bg-transparent"
        )}
      >
        <nav className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-5 py-3.5">
          <NavLink to="/" className="flex min-w-0 items-center gap-2.5">
            <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-gradient-primary text-primary-foreground">
              <BookOpen className="size-4" />
            </span>
            <span className="truncate font-display text-base font-semibold tracking-tight text-foreground">
              Booktures
            </span>
            <ApiStatus />
          </NavLink>

          <ul className="hidden items-center gap-1 md:flex">
            {navItems.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-secondary text-foreground"
                        : "text-muted-foreground hover:text-foreground"
                    )
                  }
                >
                  <item.icon className="size-3.5" />
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>

          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="inline-flex items-center justify-center rounded-md p-2 text-foreground md:hidden"
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </nav>

        {open ? (
          <div className="border-t border-border bg-background md:hidden">
            <ul className="mx-auto max-w-7xl px-5 py-3">
              {navItems.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.end}
                    onClick={() => setOpen(false)}
                    className={({ isActive }) =>
                      cn(
                        "flex items-center gap-2 rounded-md px-3 py-3 text-base font-medium transition-colors",
                        isActive
                          ? "bg-secondary text-foreground"
                          : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                      )
                    }
                  >
                    <item.icon className="size-4" />
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  );
}

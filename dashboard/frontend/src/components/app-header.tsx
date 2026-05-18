import { SidebarTrigger } from "@/components/ui/sidebar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useTheme } from "@/components/theme-provider";
import { Bell, Moon, Search, Sun } from "lucide-react";
import { useEffect, useState } from "react";
export function AppHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  const { theme, toggle } = useTheme();
  const [now, setNow] = useState("");
  useEffect(() => { const t = () => setNow(new Date().toUTCString().split(" ")[4] + " UTC"); t(); const id = setInterval(t, 1000); return () => clearInterval(id); }, []);
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-background/80 px-4 backdrop-blur-md">
      <SidebarTrigger className="-ml-1" />
      <div className="flex flex-col leading-tight"><h1 className="text-sm font-semibold">{title}</h1>{subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}</div>
      <div className="ml-auto flex items-center gap-2">
        <div className="relative hidden md:block"><Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" /><Input placeholder="Search IPs, signatures…" className="h-8 w-72 pl-8 text-xs" /></div>
        <span className="hidden text-xs tabular-nums text-muted-foreground lg:inline">{now}</span>
        <Button variant="ghost" size="icon" className="h-8 w-8"><Bell className="h-4 w-4" /></Button>
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={toggle}>{theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}</Button>
      </div>
    </header>
  );
}

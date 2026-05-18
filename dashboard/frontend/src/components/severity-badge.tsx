import { cn } from "@/lib/utils";
type Severity = "CRITICAL" | "WARNING" | "INFO";

export function SeverityBadge({ severity }: { severity: Severity }) {
  const styles: Record<Severity, string> = {
    CRITICAL: "bg-destructive/10 text-destructive ring-destructive/30",
    WARNING: "bg-warning/15 text-warning ring-warning/30",
    INFO: "bg-info/10 text-info ring-info/30",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ring-1 ring-inset",
        styles[severity],
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {severity}
    </span>
  );
}

export function StatusDot({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
      <span className={cn("h-2 w-2 rounded-full", ok ? "bg-success" : "bg-muted-foreground/40")} />
      {label}
    </span>
  );
}

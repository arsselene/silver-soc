import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

interface Props {
  label: string;
  value: string | number;
  delta?: string;
  trend?: "up" | "down" | "neutral";
  icon: LucideIcon;
  tone?: "default" | "danger" | "warning" | "success" | "info";
}

const tones: Record<NonNullable<Props["tone"]>, string> = {
  default: "text-foreground bg-muted",
  danger: "text-destructive bg-destructive/10",
  warning: "text-warning bg-warning/15",
  success: "text-success bg-success/10",
  info: "text-info bg-info/10",
};

export function KpiCard({ label, value, delta, trend, icon: Icon, tone = "default" }: Props) {
  return (
    <Card className="overflow-hidden">
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1.5">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
            <p className="text-2xl font-semibold tabular-nums tracking-tight">{value}</p>
            {delta && (
              <p
                className={cn(
                  "text-xs font-medium tabular-nums",
                  trend === "up" && "text-destructive",
                  trend === "down" && "text-success",
                  trend === "neutral" && "text-muted-foreground",
                )}
              >
                {delta}
              </p>
            )}
          </div>
          <div className={cn("flex h-9 w-9 items-center justify-center rounded-md", tones[tone])}>
            <Icon className="h-4.5 w-4.5" strokeWidth={2} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

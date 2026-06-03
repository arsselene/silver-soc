import { useState, useEffect } from "react";
import { AppHeader } from "@/components/app-header";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { api, type SoarAction, type BlockedIp } from "@/lib/api";
import { format } from "date-fns";
import { Send, Flame, Check, X } from "lucide-react";
import { cn } from "@/lib/utils";


function ActionBadge({ action }: { action: string }) {
  const colors: Record<string, string> = {
    EMERGENCY_BLOCK: "bg-destructive text-destructive-foreground",
    BLOCK:           "bg-destructive/80 text-destructive-foreground",
    SOFT_BLOCK:      "bg-orange-500/20 text-orange-400 border border-orange-500/30",
    ALERT:           "bg-yellow-500/10 text-yellow-400 border border-yellow-500/20",
    LOG_ONLY:        "bg-muted text-muted-foreground",
  };
  return <span className={cn("rounded px-2 py-0.5 text-xs font-mono font-semibold", colors[action] ?? "bg-muted text-muted-foreground")}>{action}</span>;
}

export default function SoarPage() {
  const [soar, setSoar]       = useState<SoarAction[]>([]);
  const [blocked, setBlocked] = useState<BlockedIp[]>([]);

  async function load() {
    try {
      const [s, b] = await Promise.all([api.soar(50), api.blocked()]);
      setSoar(s); setBlocked(b);
    } catch {}
  }
  useEffect(() => { load(); const id = setInterval(load, 15000); return () => clearInterval(id); }, []);

  const ts = (v: string) => { try { return format(new Date(v), "HH:mm:ss"); } catch { return v; } };

  return (
    <div className="flex min-h-screen flex-col">
      <AppHeader title="SOAR Automation" subtitle="Automated response actions and notification status" />
      <main className="flex-1 space-y-6 p-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Recent automated actions <span className="ml-2 text-muted-foreground font-normal text-xs">({soar.length})</span></CardTitle>
            <CardDescription>Multi-signal decisions — Telegram sent and firewall enforcement status</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Time</TableHead><TableHead>Source IP</TableHead><TableHead>Action</TableHead>
                  <TableHead>Reason</TableHead><TableHead className="text-right">AI Score</TableHead>
                  <TableHead>Telegram</TableHead><TableHead>Firewall</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {soar.length === 0 && <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground py-8">No SOAR actions yet</TableCell></TableRow>}
                {soar.map((a, i) => (
                  <TableRow key={i}>
                    <TableCell className="font-mono text-xs text-muted-foreground">{ts(a.timestamp)}</TableCell>
                    <TableCell className="font-mono text-xs">{a.src_ip}</TableCell>
                    <TableCell><ActionBadge action={a.action} /></TableCell>
                    <TableCell className="text-xs text-muted-foreground max-w-[200px] truncate">{a.reason}</TableCell>
                    <TableCell className="text-right font-mono text-xs tabular-nums">{a.ai_score?.toFixed(4)}</TableCell>
                    <TableCell>
                      <span className={cn("inline-flex items-center gap-1 text-xs", a.telegram_sent ? "text-green-400" : "text-muted-foreground")}>
                        <Send className="h-3 w-3" />{a.telegram_sent ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className={cn("inline-flex items-center gap-1 text-xs", a.firewall_blocked ? "text-destructive" : "text-muted-foreground")}>
                        <Flame className="h-3 w-3" />{a.firewall_blocked ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
                      </span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Blocked IPs <span className="ml-2 text-muted-foreground font-normal text-xs">({blocked.length} active)</span></CardTitle>
            <CardDescription>Currently enforced blocks — HARD blocks are permanent, SOFT blocks auto-expire</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>IP Address</TableHead><TableHead>Type</TableHead>
                  <TableHead>Reason</TableHead><TableHead>Blocked at</TableHead><TableHead>Expires</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {blocked.length === 0 && <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground py-8">No active blocks</TableCell></TableRow>}
                {blocked.map((b, i) => (
                  <TableRow key={i}>
                    <TableCell className="font-mono text-xs text-destructive">{b.ip_address}</TableCell>
                    <TableCell>
                      <Badge variant={b.block_type === "HARD" ? "destructive" : "secondary"}>{b.block_type}</Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground max-w-[200px] truncate">{b.reason}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{ts(b.blocked_at)}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{b.auto_unblock_at ? ts(b.auto_unblock_at) : "Never"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}

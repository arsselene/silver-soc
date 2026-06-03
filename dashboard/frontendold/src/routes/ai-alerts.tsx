import { Fragment, useState, useEffect } from "react";
import { AppHeader } from "@/components/app-header";
import { SeverityBadge } from "@/components/severity-badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { api, shapToArray, type Prediction } from "@/lib/api";
import { ChevronDown, ChevronRight, RefreshCw } from "lucide-react";
import { format } from "date-fns";
import { cn } from "@/lib/utils";


export default function AiAlerts() {
  const [open, setOpen]       = useState<number | null>(null);
  const [data, setData]       = useState<Prediction[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try { setData(await api.alerts(50)); } catch {}
    setLoading(false);
  }

  useEffect(() => { load(); const id = setInterval(load, 15000); return () => clearInterval(id); }, []);

  return (
    <div className="flex min-h-screen flex-col">
      <AppHeader title="AI Alerts" subtitle="ML predictions with SHAP feature attribution" />
      <main className="flex-1 space-y-6 p-6">
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle className="text-base">Recent attack predictions</CardTitle>
              <CardDescription>Click any row to inspect the top contributing features (SHAP).</CardDescription>
            </div>
            <Button size="sm" variant="outline" onClick={load} disabled={loading}>
              <RefreshCw className={cn("h-3.5 w-3.5 mr-1", loading && "animate-spin")} />Refresh
            </Button>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8" />
                  <TableHead>Time</TableHead>
                  <TableHead>Source IP</TableHead>
                  <TableHead>Destination</TableHead>
                  <TableHead>Severity</TableHead>
                  <TableHead className="text-right">Anomaly score</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.length === 0 && !loading && (
                  <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground py-8">No attacks detected yet</TableCell></TableRow>
                )}
                {data.map((p, i) => {
                  const expanded = open === i;
                  const shap = shapToArray(p.shap_top5 as Record<string,number> | null);
                  return (
                    <Fragment key={i}>
                      <TableRow className="cursor-pointer" onClick={() => setOpen(expanded ? null : i)}>
                        <TableCell>
                          {expanded ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
                        </TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {p.timestamp ? (() => { try { return format(new Date(p.timestamp), "HH:mm:ss"); } catch { return p.timestamp; } })() : "—"}
                        </TableCell>
                        <TableCell className="font-mono text-xs">{p.src_ip}</TableCell>
                        <TableCell className="font-mono text-xs">{p.dst_ip}:{p.dst_port}</TableCell>
                        <TableCell><SeverityBadge severity={p.severity} /></TableCell>
                        <TableCell className="text-right font-mono text-xs tabular-nums">{p.anomaly_score?.toFixed(4)}</TableCell>
                      </TableRow>
                      {expanded && (
                        <TableRow className="bg-muted/40 hover:bg-muted/40">
                          <TableCell />
                          <TableCell colSpan={5} className="py-4">
                            <div className="space-y-2.5">
                              <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">SHAP — top contributing features</div>
                              {shap.length === 0 && <div className="text-xs text-muted-foreground">No SHAP data for this prediction</div>}
                              {shap.map((f) => {
                                const pct = Math.min(100, Math.abs(f.value) * 200);
                                const positive = f.value >= 0;
                                return (
                                  <div key={f.feature} className="grid grid-cols-[180px_1fr_60px] items-center gap-3">
                                    <span className="font-mono text-xs">{f.feature}</span>
                                    <div className="relative h-2 rounded-full bg-muted">
                                      <div
                                        className={cn("absolute top-0 h-2 rounded-full", positive ? "left-1/2 bg-destructive" : "right-1/2 bg-blue-500")}
                                        style={{ width: `${pct / 2}%` }}
                                      />
                                      <div className="absolute left-1/2 top-[-2px] h-3 w-px bg-border" />
                                    </div>
                                    <span className={cn("text-right font-mono text-xs tabular-nums", positive ? "text-destructive" : "text-blue-400")}>
                                      {f.value > 0 ? "+" : ""}{f.value.toFixed(4)}
                                    </span>
                                  </div>
                                );
                              })}
                            </div>
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  );
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}

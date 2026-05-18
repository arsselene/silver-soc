import { useState, useEffect } from "react";
import { AppHeader } from "@/components/app-header";
import { KpiCard } from "@/components/kpi-card";
import { SeverityBadge } from "@/components/severity-badge";
import { TrafficTimeline } from "@/components/traffic-timeline";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, type Stats, type Prediction, type TopAttacker } from "@/lib/api";
import { Activity, ShieldAlert, Bug, Workflow, Ban, Zap } from "lucide-react";
import { PieChart, Pie, Cell, Legend, Tooltip, ResponsiveContainer } from "recharts";
import { format } from "date-fns";

export default function Overview() {
  const [stats, setStats]   = useState<Stats | null>(null);
  const [alerts, setAlerts] = useState<Prediction[]>([]);
  const [top, setTop]       = useState<TopAttacker[]>([]);
  const [error, setError]   = useState<string | null>(null);

  async function load() {
    try {
      const [s, a, tp] = await Promise.all([api.stats(), api.alerts(8), api.topAttackers()]);
      setStats(s); setAlerts(a); setTop(tp); setError(null);
    } catch {
      setError("Cannot reach API at localhost:8002 — is the backend running?");
    }
  }
  useEffect(() => { load(); const id = setInterval(load, 15000); return () => clearInterval(id); }, []);

  const ts = (v: string) => { try { return format(new Date(v), "HH:mm:ss"); } catch { return v; } };
  const pie = stats ? [
    { name: "Critical", value: stats.predictions.critical,  color: "var(--destructive)" },
    { name: "Warning",  value: stats.predictions.warnings,  color: "hsl(38 92% 50%)" },
    { name: "Info",     value: Math.max(0, stats.predictions.attacks - stats.predictions.critical - stats.predictions.warnings), color: "hsl(200 80% 55%)" },
  ] : [];

  return (
    <div className="flex min-h-screen flex-col">
      <AppHeader title="Overview" subtitle="Real-time situational awareness across all sensors" />
      <main className="flex-1 space-y-6 p-6">
        {error && <div className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</div>}

        {/* KPI Cards */}
        <section className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
          <KpiCard label="Total Attacks"  value={stats?.predictions.attacks?.toLocaleString() ?? "…"} delta={`${stats?.predictions.critical ?? 0} critical`} trend="up"      icon={Zap}         tone="danger"  />
          <KpiCard label="IDS Alerts"     value={stats?.suricata.total ?? "…"}                         delta="Suricata rules"      trend="up"      icon={ShieldAlert}  tone="warning" />
          <KpiCard label="Deception Hits" value={stats?.honeypot.total ?? "…"}                         delta="Cowrie honeypot"    trend="neutral" icon={Bug}          tone="info"    />
          <KpiCard label="SOAR Actions"   value={stats?.soar.total ?? "…"}                             delta="automated response" trend="neutral" icon={Workflow}     tone="success" />
          <KpiCard label="Blocked IPs"    value={stats?.blocked.total ?? "…"}                          delta="active blocks"      trend="neutral" icon={Ban}          tone="default" />
          <KpiCard label="Normal Flows"   value={stats?.predictions.normal?.toLocaleString() ?? "…"}   delta="clean traffic"      trend="down"    icon={Activity}     tone="success" />
        </section>

        {/* Advanced Timeline — full width */}
        <TrafficTimeline />

        {/* Severity + Top attackers + Live feed */}
        <section className="grid gap-4 lg:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Severity distribution</CardTitle>
              <CardDescription>Last 24 hours</CardDescription>
            </CardHeader>
            <CardContent className="h-[260px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={pie} dataKey="value" nameKey="name" innerRadius={60} outerRadius={90} paddingAngle={2} stroke="var(--card)" strokeWidth={2}>
                    {pie.map((d) => <Cell key={d.name} fill={d.color} />)}
                  </Pie>
                  <Legend iconType="circle" wrapperStyle={{ fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }} />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-base">Top attackers · 24h</CardTitle></CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader><TableRow>
                  <TableHead>IP</TableHead>
                  <TableHead className="text-right">Hits</TableHead>
                  <TableHead className="text-right">Worst</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {top.length === 0 && <TableRow><TableCell colSpan={3} className="text-center text-muted-foreground text-sm py-6">No data yet</TableCell></TableRow>}
                  {top.map((a) => (
                    <TableRow key={a.src_ip}>
                      <TableCell className="font-mono text-xs">{a.src_ip}</TableCell>
                      <TableCell className="text-right font-mono text-xs tabular-nums">{a.count}</TableCell>
                      <TableCell className="text-right font-mono text-xs tabular-nums text-destructive">{a.worst_score?.toFixed(3)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-base">Live alert feed</CardTitle></CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Time</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Sev</TableHead>
                  <TableHead className="text-right">Score</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {alerts.length === 0 && <TableRow><TableCell colSpan={4} className="text-center text-muted-foreground text-sm py-6">No attacks yet</TableCell></TableRow>}
                  {alerts.map((p, i) => (
                    <TableRow key={i}>
                      <TableCell className="font-mono text-xs text-muted-foreground">{ts(p.timestamp)}</TableCell>
                      <TableCell className="font-mono text-xs">{p.src_ip}</TableCell>
                      <TableCell><SeverityBadge severity={p.severity} /></TableCell>
                      <TableCell className="text-right font-mono text-xs tabular-nums">{p.anomaly_score?.toFixed(3)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </section>
      </main>
    </div>
  );
}

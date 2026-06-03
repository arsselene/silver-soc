import { useState, useEffect } from "react";
import { AppHeader } from "@/components/app-header";
import { SeverityBadge } from "@/components/severity-badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { api, type UebaProfile } from "@/lib/api";
import { format } from "date-fns";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Search } from "lucide-react";


export default function UebaPage() {
  const [ip, setIp]           = useState("");
  const [profile, setProfile] = useState<UebaProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);

  async function lookup() {
    const trimmed = ip.trim();
    if (!trimmed) return;
    setLoading(true); setError(null); setProfile(null);
    try {
      const p = await api.ueba(trimmed);
      setProfile(p);
    } catch {
      setError(`No profile found for ${trimmed}`);
    }
    setLoading(false);
  }

  const ts = (v: string) => { try { return format(new Date(v), "HH:mm:ss"); } catch { return v; } };

  return (
    <div className="flex min-h-screen flex-col">
      <AppHeader title="UEBA" subtitle="User and Entity Behavior Analytics — 24h behavioral profiling" />
      <main className="flex-1 space-y-6 p-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Entity behavioral profiler</CardTitle>
            <CardDescription>Enter any IP address to inspect its 24h behavioral profile stored in Redis</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex gap-2 mb-6">
              <Input
                placeholder="Enter IP address (e.g. 192.168.8.103)"
                value={ip}
                onChange={(e) => setIp(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && lookup()}
                className="font-mono"
              />
              <Button onClick={lookup} disabled={loading}>
                <Search className="h-4 w-4 mr-1" />{loading ? "Loading…" : "Inspect"}
              </Button>
            </div>

            {error && <div className="text-sm text-muted-foreground text-center py-4">{error}</div>}

            {profile && (
              <div className="space-y-6">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {[
                    { label: "IP Address",        value: profile.ip },
                    { label: "Unique Ports",       value: profile.ports_seen },
                    { label: "Unique Destinations",value: profile.dsts_seen },
                    { label: "AbuseIPDB Score",    value: `${profile.abuseipdb}/100`, danger: profile.abuseipdb >= 50 },
                  ].map((s) => (
                    <div key={s.label} className="rounded-lg border bg-card p-4">
                      <div className="text-xs text-muted-foreground mb-1">{s.label}</div>
                      <div className={`font-mono text-lg font-semibold ${s.danger ? "text-destructive" : ""}`}>{String(s.value)}</div>
                    </div>
                  ))}
                </div>

                {profile.active_hours.length > 0 && (
                  <div>
                    <div className="text-sm font-medium mb-3">24h activity heatmap</div>
                    <div className="h-[160px]">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={profile.active_hours} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                          <XAxis dataKey="hour" tickFormatter={(v) => `${v}h`} fontSize={10} tickLine={false} axisLine={false} stroke="var(--muted-foreground)" />
                          <YAxis fontSize={10} tickLine={false} axisLine={false} stroke="var(--muted-foreground)" />
                          <Tooltip contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }} labelFormatter={(v) => `Hour ${v}:00 UTC`} />
                          <Bar dataKey="count" fill="hsl(262 80% 65%)" radius={[2, 2, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )}

                {profile.ueba_alerts.length > 0 && (
                  <div>
                    <div className="text-sm font-medium mb-3">UEBA alerts for this IP</div>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Time</TableHead><TableHead>Alert Type</TableHead>
                          <TableHead>Description</TableHead><TableHead>Severity</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {profile.ueba_alerts.map((a, i) => (
                          <TableRow key={i}>
                            <TableCell className="font-mono text-xs text-muted-foreground">{ts(a.timestamp)}</TableCell>
                            <TableCell className="font-mono text-xs text-orange-400">{a.alert_type}</TableCell>
                            <TableCell className="text-xs">{a.description}</TableCell>
                            <TableCell><SeverityBadge severity={a.severity} /></TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
                {profile.ueba_alerts.length === 0 && (
                  <div className="text-sm text-muted-foreground text-center py-4">No UEBA alerts recorded for this IP</div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}

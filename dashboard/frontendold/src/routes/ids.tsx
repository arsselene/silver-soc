import { useState, useEffect } from "react";
import { AppHeader } from "@/components/app-header";
import { SeverityBadge } from "@/components/severity-badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { api, type SuricataAlert, type HoneypotAlert } from "@/lib/api";
import { format } from "date-fns";
import { Lock, ShieldOff } from "lucide-react";


export default function IdsPage() {
  const [suricata, setSuricata] = useState<SuricataAlert[]>([]);
  const [honeypot, setHoneypot] = useState<HoneypotAlert[]>([]);

  async function load() {
    try {
      const [s, h] = await Promise.all([api.suricata(30), api.honeypot(30)]);
      setSuricata(s); setHoneypot(h);
    } catch {}
  }
  useEffect(() => { load(); const id = setInterval(load, 15000); return () => clearInterval(id); }, []);

  const ts = (v: string) => { try { return format(new Date(v), "HH:mm:ss"); } catch { return v; } };

  return (
    <div className="flex min-h-screen flex-col">
      <AppHeader title="IDS & Deception" subtitle="Suricata signatures · Cowrie honeypot interactions" />
      <main className="flex-1 space-y-6 p-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Suricata alerts <span className="ml-2 text-muted-foreground font-normal text-xs">({suricata.length})</span></CardTitle>
            <CardDescription>Signature-based intrusion detection events</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Time</TableHead><TableHead>Source</TableHead><TableHead>Destination</TableHead>
                  <TableHead>Signature</TableHead><TableHead>Category</TableHead><TableHead>Severity</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {suricata.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground py-8">No Suricata alerts yet</TableCell></TableRow>}
                {suricata.map((a, i) => (
                  <TableRow key={i}>
                    <TableCell className="font-mono text-xs text-muted-foreground">{ts(a.timestamp)}</TableCell>
                    <TableCell className="font-mono text-xs">{a.src_ip}</TableCell>
                    <TableCell className="font-mono text-xs">{a.dst_ip}:{a.dst_port}</TableCell>
                    <TableCell className="text-xs">{a.signature}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{a.category}</TableCell>
                    <TableCell><SeverityBadge severity={(a.severity as "CRITICAL"|"WARNING"|"INFO") ?? "INFO"} /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Honeypot interactions <span className="ml-2 text-muted-foreground font-normal text-xs">({honeypot.length})</span></CardTitle>
            <CardDescription>Credentials tried and commands executed inside the deception environment</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Time</TableHead><TableHead>Source</TableHead><TableHead>Username</TableHead>
                  <TableHead>Password</TableHead><TableHead>Command</TableHead><TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {honeypot.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground py-8">No honeypot hits yet — waiting for attackers 🍯</TableCell></TableRow>}
                {honeypot.map((h, i) => (
                  <TableRow key={i}>
                    <TableCell className="font-mono text-xs text-muted-foreground">{ts(h.timestamp)}</TableCell>
                    <TableCell className="font-mono text-xs text-destructive">{h.src_ip}</TableCell>
                    <TableCell className="font-mono text-xs">{h.username ?? "—"}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{h.password ?? "—"}</TableCell>
                    <TableCell><code className="block max-w-md truncate rounded-md bg-muted px-2 py-1 font-mono text-xs">{h.command ?? h.event_type ?? "—"}</code></TableCell>
                    <TableCell>
                      {h.auto_blocked
                        ? <Badge variant="destructive" className="gap-1"><Lock className="h-3 w-3" />Blocked</Badge>
                        : <Badge variant="secondary" className="gap-1"><ShieldOff className="h-3 w-3" />Logged</Badge>}
                    </TableCell>
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

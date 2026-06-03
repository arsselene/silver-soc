import { useState, useEffect } from "react";
import { AppHeader } from "@/components/app-header";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { api, type BlockedIp, type IntelResult } from "@/lib/api";
import { cn } from "@/lib/utils";


function ScoreRing({ score }: { score: number }) {
  const cls = score >= 50 ? "bg-destructive/20 text-destructive border-destructive/40"
            : score >= 20 ? "bg-orange-500/10 text-orange-400 border-orange-500/30"
            :               "bg-green-500/10 text-green-400 border-green-500/30";
  return (
    <div className={cn("inline-flex h-10 w-10 items-center justify-center rounded-full border-2 font-mono text-sm font-bold", cls)}>
      {score}
    </div>
  );
}

export default function IntelPage() {
  const [entries, setEntries] = useState<{ blocked: BlockedIp; intel: IntelResult | null }[]>([]);

  async function load() {
    try {
      const blocked = await api.blocked();
      const enriched = await Promise.all(
        blocked.map(async (b) => {
          try { return { blocked: b, intel: await api.intel(b.ip_address) }; }
          catch { return { blocked: b, intel: null }; }
        })
      );
      setEntries(enriched);
    } catch {}
  }

  useEffect(() => { load(); const id = setInterval(load, 30000); return () => clearInterval(id); }, []);

  return (
    <div className="flex min-h-screen flex-col">
      <AppHeader title="Threat Intelligence" subtitle="AbuseIPDB reputation scores for blocked IPs" />
      <main className="flex-1 space-y-6 p-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">IP reputation enrichment</CardTitle>
            <CardDescription>AbuseIPDB confidence score + OTX pulse count for every blocked IP</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Score</TableHead><TableHead>IP Address</TableHead><TableHead>Country</TableHead>
                  <TableHead>ISP</TableHead><TableHead>OTX Pulses</TableHead><TableHead>Block Type</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {entries.length === 0 && (
                  <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground py-8">No blocked IPs to enrich yet</TableCell></TableRow>
                )}
                {entries.map(({ blocked: b, intel: i }, idx) => (
                  <TableRow key={idx}>
                    <TableCell><ScoreRing score={i?.abuseipdb_score ?? 0} /></TableCell>
                    <TableCell className="font-mono text-xs">{b.ip_address}</TableCell>
                    <TableCell className="text-xs">{i?.country ?? "—"}</TableCell>
                    <TableCell className="text-xs text-muted-foreground max-w-[180px] truncate">{i?.isp ?? "—"}</TableCell>
                    <TableCell className="font-mono text-xs">
                      <span className={(i?.otx_pulses ?? 0) > 5 ? "text-destructive" : "text-muted-foreground"}>
                        {i?.otx_pulses ?? 0}
                      </span>
                    </TableCell>
                    <TableCell>
                      <Badge variant={b.block_type === "HARD" ? "destructive" : "secondary"}>{b.block_type}</Badge>
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

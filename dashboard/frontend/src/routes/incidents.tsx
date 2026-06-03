import { useState, useEffect } from "react";
import { AppHeader } from "@/components/app-header";
import { SeverityBadge } from "@/components/severity-badge";
import { format } from "date-fns";
import { cn } from "@/lib/utils";
import { Shield, Brain, User, Bug, Zap, RefreshCw } from "lucide-react";

const BASE = "http://localhost:8080";

interface Incident {
  src_ip: string; alert_count: number; sources: string[];
  source_count: number; first_seen: string; last_seen: string;
  severity: string; incident_score: number; abuseipdb: number;
  country: string; flag: string; is_blocked: boolean;
}

const SOURCE_COLORS: Record<string, string> = {
  AI       : "bg-red-500/20 text-red-400 border border-red-500/30",
  Suricata : "bg-orange-500/20 text-orange-400 border border-orange-500/30",
  UEBA     : "bg-purple-500/20 text-purple-400 border border-purple-500/30",
  Honeypot : "bg-rose-500/20 text-rose-400 border border-rose-500/30",
};

function ScoreBar({ score }: { score: number }) {
  const color = score >= 75 ? "bg-red-500" : score >= 50 ? "bg-orange-500" : "bg-yellow-500";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 rounded-full bg-muted">
        <div className={cn("h-2 rounded-full transition-all", color)} style={{ width: `${score}%` }} />
      </div>
      <span className="font-mono text-xs w-6">{score}</span>
    </div>
  );
}

export default function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading]     = useState(true);
  const [hours, setHours]         = useState(24);

  async function load() {
    setLoading(true);
    try {
      const r = await fetch(`${BASE}/api/incidents?hours=${hours}`);
      setIncidents(await r.json());
    } catch {}
    setLoading(false);
  }

  useEffect(() => { load(); const id = setInterval(load, 30000); return () => clearInterval(id); }, [hours]);

  const ts = (v: string) => { try { return format(new Date(v), "MMM d HH:mm:ss"); } catch { return v; } };

  return (
    <div className="flex min-h-screen flex-col">
      <AppHeader title="Incident Correlation" subtitle="Multi-source alerts grouped into unified incidents" />
      <main className="flex-1 p-6 space-y-4">
        {/* Controls */}
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">Time window:</span>
          {[6, 24, 48, 168].map(h => (
            <button key={h} onClick={() => setHours(h)}
              className={cn("rounded px-3 py-1 text-xs font-medium border border-border",
                hours === h ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted")}>
              {h < 24 ? `${h}h` : `${h/24}d`}
            </button>
          ))}
          <button onClick={load} className="ml-auto rounded p-1.5 border border-border hover:bg-muted">
            <RefreshCw className={cn("h-3.5 w-3.5 text-muted-foreground", loading && "animate-spin")} />
          </button>
          <span className="text-xs text-muted-foreground">{incidents.length} incidents</span>
        </div>

        {/* Incident cards */}
        {incidents.length === 0 && !loading && (
          <div className="text-center text-muted-foreground text-sm py-16">
            No correlated incidents in this time window
          </div>
        )}
        <div className="space-y-3">
          {incidents.map((inc, i) => (
            <div key={i} className={cn(
              "rounded-lg border bg-card p-4",
              inc.severity === "CRITICAL" ? "border-red-500/30" : "border-orange-500/20"
            )}>
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-2 flex-1">
                  {/* Header */}
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-sm font-semibold">{inc.src_ip}</span>
                    {inc.flag && <span className="text-lg">{inc.flag}</span>}
                    <span className="text-xs text-muted-foreground">{inc.country}</span>
                    {inc.is_blocked && (
                      <span className="rounded bg-red-500/15 px-2 py-0.5 text-xs text-red-400 font-semibold">BLOCKED</span>
                    )}
                    <SeverityBadge severity={inc.severity} />
                    {inc.abuseipdb >= 50 && (
                      <span className="rounded bg-red-500/10 px-2 py-0.5 text-xs text-red-400">
                        AbuseIPDB: {inc.abuseipdb}/100
                      </span>
                    )}
                  </div>

                  {/* Sources fired */}
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs text-muted-foreground">Sources fired:</span>
                    {inc.sources.map(s => (
                      <span key={s} className={cn("rounded px-2 py-0.5 text-xs font-mono font-medium", SOURCE_COLORS[s] ?? "bg-muted text-muted-foreground")}>
                        {s}
                      </span>
                    ))}
                  </div>

                  {/* Timeline */}
                  <div className="text-xs text-muted-foreground">
                    First seen: {ts(inc.first_seen)} · Last seen: {ts(inc.last_seen)} · {inc.alert_count} total alerts
                  </div>
                </div>

                {/* Incident score */}
                <div className="flex-shrink-0 w-32 space-y-1">
                  <div className="text-xs text-muted-foreground text-right">Incident score</div>
                  <ScoreBar score={inc.incident_score} />
                  <div className="text-xs text-muted-foreground text-right">{inc.source_count} layers triggered</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}

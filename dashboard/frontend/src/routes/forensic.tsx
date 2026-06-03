import { useState } from "react";
import { AppHeader } from "@/components/app-header";
import { SeverityBadge } from "@/components/severity-badge";
import { format } from "date-fns";
import { cn } from "@/lib/utils";
import { Brain, Shield, User, Bug, Zap, Search, Lock } from "lucide-react";

const BASE = "http://localhost:8080";

const EVENT_ICONS: Record<string, React.ElementType> = {
  AI_DETECTION   : Brain,
  SURICATA_ALERT : Shield,
  UEBA_ALERT     : User,
  HONEYPOT_HIT   : Bug,
  SOAR_ACTION    : Zap,
};
const EVENT_COLORS: Record<string, string> = {
  AI_DETECTION   : "#ef4444",
  SURICATA_ALERT : "#f97316",
  UEBA_ALERT     : "#8b5cf6",
  HONEYPOT_HIT   : "#dc2626",
  SOAR_ACTION    : "#06b6d4",
};
const EVENT_LABELS: Record<string, string> = {
  AI_DETECTION   : "AI Detection",
  SURICATA_ALERT : "Suricata Alert",
  UEBA_ALERT     : "UEBA Alert",
  HONEYPOT_HIT   : "Honeypot Hit",
  SOAR_ACTION    : "SOAR Action",
};

export default function ForensicPage() {
  const [ip, setIp]         = useState("");
  const [data, setData]     = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]   = useState<string | null>(null);

  async function lookup() {
    const t = ip.trim(); if (!t) return;
    setLoading(true); setError(null); setData(null);
    try {
      const r = await fetch(`${BASE}/api/forensic/${t}`);
      if (!r.ok) throw new Error("Not found");
      setData(await r.json());
    } catch { setError(`No events found for ${t}`); }
    setLoading(false);
  }

  const ts = (v: string) => { try { return format(new Date(v), "MMM d yyyy HH:mm:ss"); } catch { return v; } };

  return (
    <div className="flex min-h-screen flex-col">
      <AppHeader title="Forensic Timeline" subtitle="Complete case file — every event for a specific IP" />
      <main className="flex-1 p-6 space-y-6">
        {/* Search */}
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="flex gap-2">
            <input
              className="flex-1 rounded-md border border-border bg-muted px-3 py-2 font-mono text-sm outline-none focus:border-primary"
              placeholder="Enter attacker IP (e.g. 192.168.8.200)"
              value={ip}
              onChange={e => setIp(e.target.value)}
              onKeyDown={e => e.key === "Enter" && lookup()}
            />
            <button onClick={lookup} disabled={loading}
              className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
              <Search className="h-4 w-4" />{loading ? "Loading…" : "Investigate"}
            </button>
          </div>
          {error && <div className="mt-2 text-sm text-muted-foreground">{error}</div>}
        </div>

        {data && (
          <>
            {/* Case header */}
            <div className="rounded-lg border border-border bg-card p-5">
              <div className="flex items-start justify-between flex-wrap gap-4">
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="font-mono text-xl font-bold">{data.ip}</span>
                    {data.intel.flag && <span className="text-2xl">{data.intel.flag}</span>}
                    {data.blocked && (
                      <span className="flex items-center gap-1 rounded bg-red-500/15 px-2 py-0.5 text-xs text-red-400 font-semibold">
                        <Lock className="h-3 w-3" />{data.blocked.block_type} BLOCK
                      </span>
                    )}
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-x-8 gap-y-1 text-xs">
                    <div><span className="text-muted-foreground">Country: </span>{data.intel.country}</div>
                    <div><span className="text-muted-foreground">City: </span>{data.intel.city || "—"}</div>
                    <div><span className="text-muted-foreground">ISP: </span>{data.intel.isp}</div>
                    <div><span className="text-muted-foreground">AbuseIPDB: </span>
                      <span className={data.intel.abuseipdb >= 50 ? "text-red-400" : ""}>{data.intel.abuseipdb}/100</span>
                    </div>
                    <div><span className="text-muted-foreground">First seen: </span>{data.first_seen ? ts(data.first_seen) : "—"}</div>
                    <div><span className="text-muted-foreground">Last seen: </span>{data.last_seen ? ts(data.last_seen) : "—"}</div>
                    <div><span className="text-muted-foreground">OTX Pulses: </span>{data.intel.otx}</div>
                    <div><span className="text-muted-foreground">Total events: </span>{data.total_events}</div>
                  </div>
                </div>

                {/* Event summary counts */}
                <div className="flex gap-3 flex-wrap">
                  {Object.entries(data.summary).map(([key, count]) => (
                    count as number > 0 && (
                      <div key={key} className="rounded-lg border border-border bg-muted/30 px-3 py-2 text-center min-w-[70px]">
                        <div className="text-lg font-bold tabular-nums" style={{ color: EVENT_COLORS[key.toUpperCase().replace('_', '_')] }}>
                          {count as number}
                        </div>
                        <div className="text-[9px] text-muted-foreground uppercase tracking-wide leading-tight">
                          {key.replace(/_/g, ' ')}
                        </div>
                      </div>
                    )
                  ))}
                </div>
              </div>
            </div>

            {/* Chronological timeline */}
            <div className="rounded-lg border border-border bg-card overflow-hidden">
              <div className="px-4 py-3 border-b border-border text-sm font-medium">
                Chronological event timeline — {data.total_events} events
              </div>
              <div className="p-4">
                {data.events.length === 0 && (
                  <div className="text-center text-muted-foreground text-sm py-8">No events recorded for this IP</div>
                )}
                <div className="relative">
                  {/* Vertical line */}
                  <div className="absolute left-6 top-0 bottom-0 w-px bg-border" />

                  <div className="space-y-4">
                    {data.events.map((ev: any, i: number) => {
                      const Icon  = EVENT_ICONS[ev.event_type] ?? Zap;
                      const color = EVENT_COLORS[ev.event_type] ?? "#475569";
                      return (
                        <div key={i} className="flex gap-4 relative">
                          {/* Icon dot */}
                          <div className="flex-shrink-0 h-12 w-12 rounded-full border-2 border-border bg-card flex items-center justify-center z-10"
                               style={{ borderColor: color }}>
                            <Icon className="h-5 w-5" style={{ color }} />
                          </div>

                          {/* Content */}
                          <div className="flex-1 rounded-lg border border-border bg-muted/20 p-3 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap mb-1">
                              <span className="text-xs font-semibold" style={{ color }}>
                                {EVENT_LABELS[ev.event_type] ?? ev.event_type}
                              </span>
                              <span className="text-xs text-muted-foreground">via {ev.source}</span>
                              <SeverityBadge severity={ev.severity} />
                              {ev.score !== null && ev.score !== undefined && (
                                <span className="ml-auto font-mono text-xs text-muted-foreground">
                                  score: {Number(ev.score).toFixed(4)}
                                </span>
                              )}
                            </div>
                            <div className="text-xs text-muted-foreground font-mono truncate">{ev.detail}</div>
                            <div className="text-[10px] text-muted-foreground/60 mt-1">{ts(ev.timestamp)}</div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

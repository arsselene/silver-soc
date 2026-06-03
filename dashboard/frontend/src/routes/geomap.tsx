import { useState, useEffect } from "react";
import { AppHeader } from "@/components/app-header";
import { RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { format } from "date-fns";

const BASE = "http://localhost:8080";

interface GeoIP {
  src_ip: string; hits: number; first_seen: string; last_seen: string;
  worst_score: number; country: string; city: string;
  lat: number | null; lon: number | null; isp: string;
  abuse: number; flag: string;
}

// Simple equirectangular projection
function geoToPixel(lat: number, lon: number, W: number, H: number) {
  const x = ((lon + 180) / 360) * W;
  const y = ((90 - lat) / 180) * H;
  return { x, y };
}

export default function GeoMapPage() {
  const [data, setData]       = useState<GeoIP[]>([]);
  const [loading, setLoading] = useState(true);
  const [hover, setHover]     = useState<GeoIP | null>(null);
  const [hoverPos, setHoverPos] = useState({ x: 0, y: 0 });

  async function load() {
    setLoading(true);
    try {
      const r = await fetch(`${BASE}/api/geoip/map`);
      setData(await r.json());
    } catch {}
    setLoading(false);
  }

  useEffect(() => { load(); const id = setInterval(load, 60000); return () => clearInterval(id); }, []);

  const ts = (v: string) => { try { return format(new Date(v), "MMM d HH:mm"); } catch { return v; } };
  const W = 960, H = 480;

  // Group by country for stats
  const byCountry: Record<string, number> = {};
  data.forEach(d => { byCountry[d.country] = (byCountry[d.country] || 0) + d.hits; });
  const topCountries = Object.entries(byCountry).sort((a, b) => b[1] - a[1]).slice(0, 8);

  const withGeo = data.filter(d => d.lat !== null && d.lon !== null);

  return (
    <div className="flex min-h-screen flex-col">
      <AppHeader title="GeoIP Attack Map" subtitle="World map of attack origins — last 7 days" />
      <main className="flex-1 p-6 space-y-4">
        {/* Stats bar */}
        <div className="flex items-center gap-4">
          <div className="text-xs text-muted-foreground">{data.length} unique attacker IPs</div>
          <div className="text-xs text-muted-foreground">{withGeo.length} with geo data</div>
          <div className="text-xs text-muted-foreground">{Object.keys(byCountry).length} countries</div>
          <button onClick={load} className="ml-auto rounded p-1.5 border border-border hover:bg-muted">
            <RefreshCw className={cn("h-3.5 w-3.5 text-muted-foreground", loading && "animate-spin")} />
          </button>
        </div>

        <div className="grid grid-cols-4 gap-4">
          {/* World map SVG */}
          <div className="col-span-3 rounded-lg border border-border bg-card overflow-hidden relative">
            <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ background: '#0f172a' }}>
              {/* Simple world map background grid */}
              {Array.from({ length: 13 }).map((_, i) => (
                <line key={`v${i}`} x1={(i/12)*W} y1={0} x2={(i/12)*W} y2={H}
                  stroke="rgba(255,255,255,0.05)" strokeWidth={0.5} />
              ))}
              {Array.from({ length: 7 }).map((_, i) => (
                <line key={`h${i}`} x1={0} y1={(i/6)*H} x2={W} y2={(i/6)*H}
                  stroke="rgba(255,255,255,0.05)" strokeWidth={0.5} />
              ))}

              {/* Equator and prime meridian */}
              <line x1={0} y1={H/2} x2={W} y2={H/2} stroke="rgba(255,255,255,0.1)" strokeWidth={1} />
              <line x1={W/2} y1={0} x2={W/2} y2={H} stroke="rgba(255,255,255,0.1)" strokeWidth={1} />

              {/* Attack dots */}
              {withGeo.map((ip, i) => {
                const { x, y } = geoToPixel(ip.lat!, ip.lon!, W, H);
                const r = Math.min(16, 4 + Math.log(ip.hits + 1) * 2.5);
                const isHighAbuse = ip.abuse >= 50;
                return (
                  <g key={i}>
                    {/* Pulse ring */}
                    <circle cx={x} cy={y} r={r + 4} fill="none"
                      stroke={isHighAbuse ? "rgba(239,68,68,0.4)" : "rgba(251,146,60,0.3)"}
                      strokeWidth={1.5} />
                    {/* Main dot */}
                    <circle cx={x} cy={y} r={r}
                      fill={isHighAbuse ? "#ef4444" : "#f97316"}
                      fillOpacity={0.85}
                      style={{ cursor: 'pointer' }}
                      onMouseEnter={(e) => {
                        setHover(ip);
                        const rect = (e.target as SVGElement).closest('svg')!.getBoundingClientRect();
                        setHoverPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
                      }}
                      onMouseLeave={() => setHover(null)}
                    />
                    {/* Flag */}
                    {ip.flag && (
                      <text x={x} y={y + 1} textAnchor="middle" dominantBaseline="middle"
                        fontSize={r > 8 ? 10 : 7} style={{ pointerEvents: 'none' }}>
                        {ip.flag}
                      </text>
                    )}
                  </g>
                );
              })}
            </svg>

            {/* Hover tooltip */}
            {hover && (
              <div className="absolute pointer-events-none rounded-lg border border-border bg-card/95 p-3 text-xs shadow-xl z-10 min-w-[180px]"
                style={{ left: Math.min(hoverPos.x + 10, W - 200), top: Math.max(hoverPos.y - 80, 8) }}>
                <div className="font-mono font-semibold mb-1">{hover.flag} {hover.src_ip}</div>
                <div className="text-muted-foreground">{hover.city ? `${hover.city}, ` : ""}{hover.country}</div>
                <div className="text-muted-foreground">{hover.isp}</div>
                <div className="mt-1 space-y-0.5">
                  <div>Attacks: <span className="text-red-400 font-semibold">{hover.hits}</span></div>
                  <div>AbuseIPDB: <span className={hover.abuse >= 50 ? "text-red-400" : ""}>{hover.abuse}/100</span></div>
                  <div>Last seen: {ts(hover.last_seen)}</div>
                </div>
              </div>
            )}

            {/* No geo data warning */}
            {withGeo.length === 0 && !loading && (
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="text-center text-muted-foreground text-sm p-8">
                  <div className="mb-2">No geo coordinates available yet.</div>
                  <div className="text-xs">The intel enricher stores lat/lon in Redis when AbuseIPDB returns them.</div>
                  <div className="text-xs mt-1">Make sure the intel enricher is running and attacks have been detected.</div>
                </div>
              </div>
            )}
          </div>

          {/* Top countries sidebar */}
          <div className="space-y-4">
            <div className="rounded-lg border border-border bg-card p-4">
              <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
                Top attack origins
              </div>
              <div className="space-y-2">
                {topCountries.map(([country, hits]) => {
                  const maxHits = topCountries[0][1];
                  return (
                    <div key={country}>
                      <div className="flex justify-between text-xs mb-0.5">
                        <span>{country}</span>
                        <span className="text-red-400 font-mono">{hits}</span>
                      </div>
                      <div className="h-1.5 rounded-full bg-muted">
                        <div className="h-1.5 rounded-full bg-red-500"
                          style={{ width: `${(hits / maxHits) * 100}%` }} />
                      </div>
                    </div>
                  );
                })}
                {topCountries.length === 0 && (
                  <div className="text-xs text-muted-foreground">No country data yet</div>
                )}
              </div>
            </div>

            {/* Recent attackers list */}
            <div className="rounded-lg border border-border bg-card p-4">
              <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
                Top attackers
              </div>
              <div className="space-y-2">
                {data.slice(0, 8).map((d, i) => (
                  <div key={i} className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5 min-w-0">
                      {d.flag && <span className="text-sm flex-shrink-0">{d.flag}</span>}
                      <span className="font-mono text-xs truncate">{d.src_ip}</span>
                    </div>
                    <span className="text-xs text-red-400 font-mono flex-shrink-0">{d.hits}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

import { useState, useEffect, useRef } from "react";
import { AppHeader } from "@/components/app-header";
import { RefreshCw, ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";

const BASE = "http://localhost:8080";

interface Node { id: string; type: string; attacks: number; country: string; abuse: number; blocked: boolean; }
interface Edge { source: string; target: string; port: string; flow_count: number; is_attack: boolean; color: string; width: number; }
interface Topology { nodes: Node[]; edges: Edge[]; stats: { total_nodes: number; total_edges: number; attack_edges: number } }
interface ForensicData { total_events: number; first_seen: string; last_seen: string; intel: any; blocked: any; summary: any; events: any[]; }

export default function TopologyPage() {
  const [topo, setTopo]             = useState<Topology | null>(null);
  const [loading, setLoading]       = useState(true);
  const [selected, setSelected]     = useState<string | null>(null);
  const [forensic, setForensic]     = useState<ForensicData | null>(null);
  const [loadingF, setLoadingF]     = useState(false);
  const canvasRef                   = useRef<HTMLCanvasElement>(null);
  const positions                   = useRef<Record<string, { x: number; y: number }>>({});

  async function load() {
    setLoading(true);
    try {
      const r = await fetch(`${BASE}/api/topology?limit=80`);
      const data = await r.json();
      setTopo(data);
    } catch {}
    setLoading(false);
  }

  async function loadForensic(ip: string) {
    setLoadingF(true);
    setForensic(null);
    try {
      const r = await fetch(`${BASE}/api/forensic/${ip}`);
      const data = await r.json();
      setForensic(data);
    } catch {}
    setLoadingF(false);
  }

  useEffect(() => { load(); const id = setInterval(load, 30000); return () => clearInterval(id); }, []);

  useEffect(() => {
    if (!topo || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx    = canvas.getContext('2d')!;
    const W      = canvas.width;
    const H      = canvas.height;

    topo.nodes.forEach((node, i) => {
      if (!positions.current[node.id]) {
        const angle  = (i / topo.nodes.length) * 2 * Math.PI;
        const radius = Math.min(W, H) * 0.35;
        positions.current[node.id] = {
          x: W / 2 + radius * Math.cos(angle) + (Math.random() - 0.5) * 60,
          y: H / 2 + radius * Math.sin(angle) + (Math.random() - 0.5) * 60,
        };
      }
    });

    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(0, 0, W, H);

    topo.edges.forEach(edge => {
      const src = positions.current[edge.source];
      const dst = positions.current[edge.target];
      if (!src || !dst) return;
      ctx.beginPath();
      ctx.moveTo(src.x, src.y);
      ctx.lineTo(dst.x, dst.y);
      ctx.strokeStyle = edge.is_attack ? 'rgba(239,68,68,0.6)' : 'rgba(6,182,212,0.3)';
      ctx.lineWidth   = edge.width;
      ctx.stroke();
      const angle = Math.atan2(dst.y - src.y, dst.x - src.x);
      const tipX  = dst.x - 12 * Math.cos(angle);
      const tipY  = dst.y - 12 * Math.sin(angle);
      ctx.beginPath();
      ctx.moveTo(tipX, tipY);
      ctx.lineTo(tipX - 8 * Math.cos(angle - 0.4), tipY - 8 * Math.sin(angle - 0.4));
      ctx.lineTo(tipX - 8 * Math.cos(angle + 0.4), tipY - 8 * Math.sin(angle + 0.4));
      ctx.closePath();
      ctx.fillStyle = edge.is_attack ? 'rgba(239,68,68,0.8)' : 'rgba(6,182,212,0.5)';
      ctx.fill();
    });

    topo.nodes.forEach(node => {
      const pos = positions.current[node.id];
      if (!pos) return;
      const isSelected = node.id === selected;
      const nodeR = node.type === 'attacker' ? 10 : 8;

      if (node.type === 'attacker') {
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, nodeR + 6, 0, 2 * Math.PI);
        ctx.fillStyle = 'rgba(239,68,68,0.15)';
        ctx.fill();
      }

      if (isSelected) {
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, nodeR + 8, 0, 2 * Math.PI);
        ctx.fillStyle = 'rgba(255,255,255,0.25)';
        ctx.fill();
      }

      ctx.beginPath();
      ctx.arc(pos.x, pos.y, nodeR, 0, 2 * Math.PI);
      ctx.fillStyle = node.blocked      ? '#7f1d1d'
                    : node.type === 'attacker' ? '#ef4444'
                    : node.type === 'target'   ? '#06b6d4'
                    :                            '#475569';
      ctx.fill();

      if (isSelected) {
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth   = 2.5;
        ctx.stroke();
      }

      ctx.fillStyle  = 'rgba(255,255,255,0.7)';
      ctx.font       = '9px monospace';
      ctx.textAlign  = 'center';
      ctx.fillText(node.id.split('.').slice(-2).join('.'), pos.x, pos.y + nodeR + 10);
    });

  }, [topo, selected]);

  // ── FIX: scale mouse coords to canvas coords ──────────────
  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!topo || !canvasRef.current) return;
    const canvas  = canvasRef.current;
    const rect    = canvas.getBoundingClientRect();

    // Scale factor between CSS pixels and canvas pixels
    const scaleX  = canvas.width  / rect.width;
    const scaleY  = canvas.height / rect.height;

    const mx = (e.clientX - rect.left)  * scaleX;
    const my = (e.clientY - rect.top)   * scaleY;

    for (const node of topo.nodes) {
      const pos = positions.current[node.id];
      if (!pos) continue;
      const dist = Math.sqrt((mx - pos.x) ** 2 + (my - pos.y) ** 2);
      if (dist < 16) {
        const newSelected = node.id === selected ? null : node.id;
        setSelected(newSelected);
        if (newSelected) loadForensic(newSelected);
        else setForensic(null);
        return;
      }
    }
    setSelected(null);
    setForensic(null);
  };

  const selectedNode = topo?.nodes.find(n => n.id === selected);

  return (
    <div className="flex min-h-screen flex-col">
      <AppHeader title="Network Topology" subtitle="Live traffic graph — attack flows in red, normal in cyan" />
      <main className="flex-1 p-6 space-y-4">
        <div className="flex items-center gap-4">
          {topo && (
            <>
              <div className="text-xs text-muted-foreground">{topo.stats.total_nodes} nodes</div>
              <div className="text-xs text-muted-foreground">{topo.stats.total_edges} connections</div>
              <div className="text-xs text-red-400">{topo.stats.attack_edges} attack flows</div>
            </>
          )}
          <button onClick={load} className="ml-auto rounded p-1.5 border border-border hover:bg-muted">
            <RefreshCw className={cn("h-3.5 w-3.5 text-muted-foreground", loading && "animate-spin")} />
          </button>
        </div>

        <div className="grid grid-cols-4 gap-4">
          {/* Canvas */}
          <div className="col-span-3 rounded-lg border border-border bg-card overflow-hidden">
            <canvas
              ref={canvasRef}
              width={900} height={600}
              className="w-full h-full cursor-crosshair"
              onClick={handleCanvasClick}
            />
          </div>

          {/* Right panel */}
          <div className="space-y-4">
            {/* Legend */}
            <div className="rounded-lg border border-border bg-card p-4 space-y-3">
              <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Legend</div>
              {[
                { color: "#ef4444", label: "Attacker node" },
                { color: "#06b6d4", label: "Target node" },
                { color: "#475569", label: "Normal host" },
                { color: "#7f1d1d", label: "Blocked IP" },
              ].map(l => (
                <div key={l.label} className="flex items-center gap-2">
                  <div className="h-3 w-3 rounded-full flex-shrink-0" style={{ background: l.color }} />
                  <span className="text-xs text-muted-foreground">{l.label}</span>
                </div>
              ))}
              <div className="border-t border-border pt-2 space-y-1">
                <div className="flex items-center gap-2">
                  <div className="h-0.5 w-6 bg-red-500" />
                  <span className="text-xs text-muted-foreground">Attack flow</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="h-0.5 w-6 bg-cyan-500/50" />
                  <span className="text-xs text-muted-foreground">Normal flow</span>
                </div>
              </div>
              <div className="text-xs text-muted-foreground pt-1">Click a node to inspect</div>
            </div>

            {/* Selected node basic info */}
            {selectedNode && (
              <div className="rounded-lg border border-border bg-card p-4 space-y-2">
                <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Selected Node
                </div>
                <div className="font-mono text-sm font-semibold">{selectedNode.id}</div>
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Type</span>
                    <span className="capitalize">{selectedNode.type}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Country</span>
                    <span>{selectedNode.country || "—"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Attacks</span>
                    <span className="text-red-400">{selectedNode.attacks}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">AbuseIPDB</span>
                    <span className={selectedNode.abuse >= 50 ? "text-red-400" : ""}>
                      {selectedNode.abuse}/100
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Blocked</span>
                    <span className={selectedNode.blocked ? "text-red-400" : "text-green-400"}>
                      {selectedNode.blocked ? "Yes" : "No"}
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Forensic summary panel */}
            {loadingF && (
              <div className="rounded-lg border border-border bg-card p-4">
                <div className="text-xs text-muted-foreground animate-pulse">Loading forensic data...</div>
              </div>
            )}

            {forensic && !loadingF && (
              <div className="rounded-lg border border-border bg-card p-4 space-y-3">
                <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Forensic Summary
                </div>

                {/* Intel */}
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">City</span>
                    <span>{forensic.intel?.city || "—"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">ISP</span>
                    <span className="truncate max-w-[120px] text-right">
                      {forensic.intel?.isp || "—"}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Total events</span>
                    <span className="font-semibold">{forensic.total_events}</span>
                  </div>
                </div>

                {/* Event breakdown */}
                <div className="border-t border-border pt-2 space-y-1 text-xs">
                  {forensic.summary.ai_detections > 0 && (
                    <div className="flex justify-between">
                      <span className="text-red-400">AI detections</span>
                      <span>{forensic.summary.ai_detections}</span>
                    </div>
                  )}
                  {forensic.summary.suricata_alerts > 0 && (
                    <div className="flex justify-between">
                      <span className="text-orange-400">Suricata alerts</span>
                      <span>{forensic.summary.suricata_alerts}</span>
                    </div>
                  )}
                  {forensic.summary.ueba_alerts > 0 && (
                    <div className="flex justify-between">
                      <span className="text-purple-400">UEBA alerts</span>
                      <span>{forensic.summary.ueba_alerts}</span>
                    </div>
                  )}
                  {forensic.summary.honeypot_hits > 0 && (
                    <div className="flex justify-between">
                      <span className="text-red-600">Honeypot hits</span>
                      <span>{forensic.summary.honeypot_hits}</span>
                    </div>
                  )}
                  {forensic.summary.soar_actions > 0 && (
                    <div className="flex justify-between">
                      <span className="text-cyan-400">SOAR actions</span>
                      <span>{forensic.summary.soar_actions}</span>
                    </div>
                  )}
                </div>

                {/* Block status */}
                {forensic.blocked && (
                  <div className="border-t border-border pt-2">
                    <div className="rounded bg-red-950/40 border border-red-800/40 p-2 text-xs space-y-1">
                      <div className="text-red-400 font-semibold">
                        BLOCKED — {forensic.blocked.block_type}
                      </div>
                      <div className="text-muted-foreground">{forensic.blocked.reason}</div>
                    </div>
                  </div>
                )}

                {/* Last 3 events */}
                {forensic.events.length > 0 && (
                  <div className="border-t border-border pt-2 space-y-1">
                    <div className="text-xs text-muted-foreground font-semibold mb-1">
                      Last events
                    </div>
                    {forensic.events.slice(-3).reverse().map((ev: any, i: number) => (
                      <div key={i} className="text-xs border-l-2 pl-2 py-0.5"
                           style={{ borderColor: ev.color }}>
                        <div className="font-medium" style={{ color: ev.color }}>
                          {ev.source}
                        </div>
                        <div className="text-muted-foreground truncate">{ev.detail}</div>
                        <div className="text-muted-foreground/60">
                          {new Date(ev.timestamp).toLocaleTimeString()}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
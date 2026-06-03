import { useState, useEffect, useRef } from "react";
import { fetchTimeline, type TimelinePoint } from "@/lib/api";
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer,
  Tooltip, XAxis, YAxis, Legend,
} from "recharts";
import { format, subHours } from "date-fns";
import { RefreshCw, Clock } from "lucide-react";
import { cn } from "@/lib/utils";

// ── Types ─────────────────────────────────────────────────────
interface PanelDef {
  label: string;
  metric: "attacks" | "normal";
  color: string;
  gran: "minute" | "hour" | "day";
  hours: number;
}

const PANEL_DEFS: PanelDef[] = [
  { label: "Attacks (24h)",     metric: "attacks", color: "#ef4444", gran: "hour", hours: 24  },
  { label: "Normal flows (24h)",metric: "normal",  color: "#06b6d4", gran: "hour", hours: 24  },
  { label: "Attacks (7d)",      metric: "attacks", color: "#f97316", gran: "day",  hours: 168 },
  { label: "Normal (7d)",       metric: "normal",  color: "#10b981", gran: "day",  hours: 168 },
];

const PRESETS = [
  { label: "2h",  hours: 2,   gran: "hour" as const },
  { label: "6h",  hours: 6,   gran: "hour" as const },
  { label: "24h", hours: 24,  gran: "hour" as const },
  { label: "7d",  hours: 168, gran: "day"  as const },
];

function toLocal(iso: string) {
  const d = new Date(iso);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
function fromLocal(v: string) { return new Date(v).toISOString(); }

// ── Sparkline Panel ──────────────────────────────────────────
function SparkPanel({ def, data, loading }: { def: PanelDef; data: TimelinePoint[]; loading: boolean }) {
  const chartData = data.map(pt => ({ t: pt.t, v: def.metric === "attacks" ? pt.attacks : pt.normal }));
  const total = chartData.reduce((s, d) => s + d.v, 0);
  const peak  = Math.max(...chartData.map(d => d.v), 0);
  const last  = chartData.at(-1)?.v ?? 0;

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      <div className="flex items-center justify-between px-3 pt-3 pb-0.5">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{def.label}</span>
        {loading && <RefreshCw className="h-3 w-3 animate-spin text-muted-foreground" />}
      </div>
      <div className="flex items-end gap-3 px-3 pb-1">
        <span className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: def.color }}>
          {total.toLocaleString()}
        </span>
        <div className="mb-0.5 text-[9px] leading-tight text-muted-foreground">
          <div>last: {last}</div>
          <div>peak: {peak}</div>
        </div>
      </div>
      <div className="h-[72px]">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id={`sp_${def.label.replace(/\s/g,'_')}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"   stopColor={def.color} stopOpacity={0.45} />
                <stop offset="100%" stopColor={def.color} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <XAxis dataKey="t" hide />
            <YAxis hide />
            <Tooltip
              contentStyle={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 6, fontSize: 10 }}
              labelFormatter={(v) => { try { return format(new Date(v as string), "HH:mm · MMM d"); } catch { return String(v); } }}
              formatter={(v: number) => [v, def.metric]}
            />
            <Area type="monotone" dataKey="v"
              stroke={def.color} strokeWidth={1.5}
              fill={`url(#sp_${def.label.replace(/\s/g,'_')})`}
              dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ── Main component ───────────────────────────────────────────
export function TrafficTimeline() {
  const [sparkData,   setSparkData]   = useState<TimelinePoint[][]>(PANEL_DEFS.map(() => []));
  const [sparkLoad,   setSparkLoad]   = useState<boolean[]>(PANEL_DEFS.map(() => false));
  const [mainData,    setMainData]    = useState<TimelinePoint[]>([]);
  const [mainLoading, setMainLoading] = useState(false);
  const [mainFrom,    setMainFrom]    = useState(() => subHours(new Date(), 24).toISOString());
  const [mainTo,      setMainTo]      = useState(() => new Date().toISOString());
  const [mainGran,    setMainGran]    = useState<"minute"|"hour"|"day">("hour");
  const [activePreset,setActivePreset]= useState("24h");
  const [showCustom,  setShowCustom]  = useState(false);
  const [customFrom,  setCustomFrom]  = useState("");
  const [customTo,    setCustomTo]    = useState("");

  const mainFromRef = useRef(mainFrom);
  const mainToRef   = useRef(mainTo);
  const mainGranRef = useRef(mainGran);
  mainFromRef.current = mainFrom;
  mainToRef.current   = mainTo;
  mainGranRef.current = mainGran;

  // Load all sparklines on mount
  async function loadSparklines() {
    PANEL_DEFS.forEach(async (def, i) => {
      setSparkLoad(prev => { const n = [...prev]; n[i] = true; return n; });
      try {
        const from = subHours(new Date(), def.hours).toISOString();
        const data = await fetchTimeline({ from, to: new Date().toISOString(), granularity: def.gran });
        setSparkData(prev => { const n = [...prev]; n[i] = data; return n; });
      } catch {}
      setSparkLoad(prev => { const n = [...prev]; n[i] = false; return n; });
    });
  }

  // Load main chart
  async function loadMain(from?: string, to?: string, gran?: "minute"|"hour"|"day") {
    const f = from ?? mainFromRef.current;
    const t = to   ?? mainToRef.current;
    const g = gran ?? mainGranRef.current;
    setMainLoading(true);
    try {
      const data = await fetchTimeline({ from: f, to: t, granularity: g });
      setMainData(data);
    } catch {}
    setMainLoading(false);
  }

  useEffect(() => {
    loadSparklines();
    loadMain();
    const id = setInterval(() => { loadSparklines(); loadMain(); }, 60000);
    return () => clearInterval(id);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function applyPreset(hours: number, gran: "minute"|"hour"|"day", label: string) {
    const now  = new Date();
    const from = subHours(now, hours).toISOString();
    const to   = now.toISOString();
    setMainFrom(from); setMainTo(to); setMainGran(gran);
    setActivePreset(label); setShowCustom(false);
    loadMain(from, to, gran);
  }

  function applyCustom() {
    if (!customFrom || !customTo) return;
    const from = fromLocal(customFrom);
    const to   = fromLocal(customTo);
    setMainFrom(from); setMainTo(to);
    setActivePreset("custom");
    loadMain(from, to, mainGran);
  }

  // Build merged chart data
  const merged = mainData.map(pt => ({
    _t: pt.t,
    _label: (() => { try { return format(new Date(pt.t), mainGran === "day" ? "MMM d" : "HH:mm"); } catch { return String(pt.t); } })(),
    attacks: pt.attacks,
    normal:  pt.normal,
  }));

  return (
    <div className="space-y-4">
      {/* ── 4 sparkline panels ─────────────────────────── */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {PANEL_DEFS.map((def, i) => (
          <SparkPanel key={def.label} def={def} data={sparkData[i]} loading={sparkLoad[i]} />
        ))}
      </div>

      {/* ── Combined chart with time controls ──────────── */}
      <div className="rounded-lg border border-border bg-card overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-2 flex-wrap border-b border-border px-4 py-2.5">
          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mr-1">
            Traffic timeline
          </span>
          {PRESETS.map(p => (
            <button key={p.label} onClick={() => applyPreset(p.hours, p.gran, p.label)}
              className={cn("rounded px-2.5 py-1 text-xs font-medium transition-colors",
                activePreset === p.label
                  ? "bg-primary text-primary-foreground"
                  : "border border-border text-muted-foreground hover:bg-muted hover:text-foreground")}>
              {p.label}
            </button>
          ))}
          <button onClick={() => setShowCustom(!showCustom)}
            className={cn("rounded px-2.5 py-1 text-xs font-medium border border-border transition-colors",
              showCustom || activePreset === "custom"
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground")}>
            <Clock className="inline h-3 w-3 mr-1" />Custom
          </button>
          <div className="flex gap-1 border-l border-border pl-2 ml-1">
            {(["minute","hour","day"] as const).map(g => (
              <button key={g} onClick={() => { setMainGran(g); loadMain(undefined, undefined, g); }}
                className={cn("rounded px-2 py-1 text-xs capitalize",
                  mainGran === g ? "bg-muted text-foreground font-medium" : "text-muted-foreground hover:text-foreground")}>
                {g}
              </button>
            ))}
          </div>
          <button onClick={() => loadMain()} className="ml-auto rounded p-1.5 hover:bg-muted">
            <RefreshCw className={cn("h-3.5 w-3.5 text-muted-foreground", mainLoading && "animate-spin")} />
          </button>
        </div>

        {/* Custom date picker */}
        {showCustom && (
          <div className="flex items-center gap-2 flex-wrap border-b border-border bg-muted/20 px-4 py-2">
            <span className="text-xs text-muted-foreground">From</span>
            <input type="datetime-local"
              defaultValue={toLocal(mainFrom)}
              onChange={e => setCustomFrom(e.target.value)}
              className="rounded border border-border bg-background px-2 py-1 font-mono text-xs outline-none focus:border-primary" />
            <span className="text-xs text-muted-foreground">To</span>
            <input type="datetime-local"
              defaultValue={toLocal(mainTo)}
              onChange={e => setCustomTo(e.target.value)}
              className="rounded border border-border bg-background px-2 py-1 font-mono text-xs outline-none focus:border-primary" />
            <button onClick={applyCustom}
              className="rounded bg-primary px-3 py-1 text-xs font-medium text-primary-foreground">
              Apply
            </button>
            <span className="ml-auto text-xs text-muted-foreground">{mainData.length} data points</span>
          </div>
        )}

        {/* Chart */}
        <div className="h-[260px] px-2 pb-3 pt-2">
          {merged.length === 0 ? (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              {mainLoading ? "Loading…" : "No data for selected range"}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={merged} margin={{ top: 8, right: 16, left: -12, bottom: 0 }}>
                <defs>
                  <linearGradient id="main_atk" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%"   stopColor="#ef4444" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="#ef4444" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="main_nrm" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%"   stopColor="#06b6d4" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#06b6d4" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="rgba(255,255,255,0.06)" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="_label" fontSize={10} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                <YAxis fontSize={10} tickLine={false} axisLine={false} />
                <Tooltip
                  contentStyle={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8, fontSize: 11 }}
                  labelFormatter={(v) => { try { return format(new Date(v as string), "HH:mm · MMM d"); } catch { return String(v); } }}
                />
                <Legend iconType="circle" wrapperStyle={{ fontSize: 11, paddingTop: 4 }} />
                <Area type="monotone" dataKey="normal"  name="Normal"  stroke="#06b6d4" strokeWidth={1.5} fill="url(#main_nrm)" dot={false} activeDot={{ r: 3 }} />
                <Area type="monotone" dataKey="attacks" name="Attacks" stroke="#ef4444" strokeWidth={2}   fill="url(#main_atk)" dot={false} activeDot={{ r: 3 }} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  );
}

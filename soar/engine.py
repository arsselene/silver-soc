import json
import logging
import os
import time
import requests
import psycopg2
import redis
from confluent_kafka import Consumer, Producer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("Mobilis-SOAR")

KAFKA_BOOTSTRAP  = os.getenv("KAFKA_BOOTSTRAP",             "kafka:29092")
DATABASE_URL     = os.getenv("DATABASE_URL",                "postgresql://mobilis_admin:Mob1l1s%40SOC2025@postgres:5432/mobilis_soc")
REDIS_HOST       = os.getenv("REDIS_HOST",                  "redis")
REDIS_PORT       = int(os.getenv("REDIS_PORT",              "6379"))
REDIS_PASSWORD   = os.getenv("REDIS_PASSWORD",              "R3d1s@SOC2025")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN",          "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID",            "")
SOFT_BLOCK_MIN   = int(os.getenv("SOFT_BLOCK_MINUTES",      "10"))
BLOCK_THRESHOLD  = int(os.getenv("ABUSEIPDB_BLOCK_THRESHOLD","50"))
AI_THRESHOLD_ZD  = float(os.getenv("AI_THRESHOLD_ZERO_DAY", "-0.0500"))

# Telegram cooldown per action type (seconds)
TG_COOLDOWN = {
    "EMERGENCY_BLOCK": 60,    # 1 min — always important
    "BLOCK"          : 300,   # 5 min
    "SOFT_BLOCK"     : 600,   # 10 min
    "ALERT"          : 1800,  # 30 min — reduce noise
}

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT,
                password=REDIS_PASSWORD, decode_responses=True)

def send_telegram(message: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"},
            timeout=5
        )
        if resp.status_code == 200:
            log.info("📱 Telegram sent")
            return True
        log.warning(f"Telegram failed: {resp.status_code}")
    except Exception as e:
        log.error(f"Telegram error: {e}")
    return False

def db_insert(query, params):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur  = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        log.error(f"DB error: {e}")

def log_soar_action(src_ip, action, reason, ai_score, abuseipdb_score,
                    suricata_fired, ueba_fired, honeypot_fired,
                    telegram_sent, firewall_blocked):
    db_insert("""
        INSERT INTO soar_actions
        (src_ip,action,reason,ai_score,abuseipdb_score,
         suricata_fired,ueba_fired,honeypot_fired,telegram_sent,firewall_blocked)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (src_ip,action,reason,ai_score,abuseipdb_score,
          suricata_fired,ueba_fired,honeypot_fired,telegram_sent,firewall_blocked))

def log_blocked_ip(ip, block_type, reason, minutes=None):
    unblock_at = None
    if minutes:
        unblock_at = time.strftime("%Y-%m-%d %H:%M:%S",
                                   time.gmtime(time.time() + minutes * 60))
    db_insert("""
        INSERT INTO blocked_ips (ip_address,block_type,reason,auto_unblock_at)
        VALUES (%s,%s,%s,%s)
        ON CONFLICT (ip_address) DO UPDATE
        SET block_type=EXCLUDED.block_type, reason=EXCLUDED.reason,
            blocked_at=CURRENT_TIMESTAMP, unblocked=FALSE
    """, (ip, block_type, reason, unblock_at))

def decide(event: dict) -> tuple[str, str]:
    """
    Multi-signal SOAR decision engine.

    EMERGENCY_BLOCK  = honeypot hit (zero tolerance)
    BLOCK            = AI anomaly + AbuseIPDB > 50 + Suricata fired
    SOFT_BLOCK       = extreme AI score + UEBA anomaly
    ALERT            = AI anomaly + at least 1 other gate
    LOG_ONLY         = UEBA or Suricata alone (no AI confirmation) — no Telegram
    NORMAL           = nothing fired
    """
    src_ip         = event.get("src_ip", "")
    ai_score       = float(event.get("ai_score", 1.0))
    suricata_fired = bool(event.get("suricata_fired", False))
    ueba_fired     = bool(event.get("ueba_fired", False))
    honeypot_fired = bool(event.get("honeypot_fired", False))

    abuse_str = r.get(f"intel:{src_ip}:abuseipdb")
    abuse_score = int(abuse_str) if abuse_str else 0

    if not ueba_fired:
        ueba_fired     = r.exists(f"ueba:alert:{src_ip}") == 1
    if not honeypot_fired:
        honeypot_fired = r.exists(f"honeypot:hit:{src_ip}") == 1
    if not suricata_fired:
        suricata_fired = r.exists(f"suricata:recent:{src_ip}") == 1

    ai_fired   = ai_score < -0.0161   # below calibrated threshold
    zeroday_ai = ai_score < AI_THRESHOLD_ZD

    # Gate 0 — honeypot (unconditional)
    if honeypot_fired:
        return "EMERGENCY_BLOCK", "Honeypot hit — zero tolerance"

    # Gate 1 — all 3 hard gates
    if ai_fired and abuse_score >= BLOCK_THRESHOLD and suricata_fired:
        return "BLOCK", f"All 3 gates: AI({ai_score:.3f}) + AbuseIPDB({abuse_score}) + Suricata"

    # Gate 2 — zero-day pattern
    if zeroday_ai and ueba_fired:
        return "SOFT_BLOCK", f"Zero-day: AI({ai_score:.3f}) + UEBA"

    if zeroday_ai:
        return "SOFT_BLOCK", f"Extreme AI score: {ai_score:.3f}"

    # Gate 3 — AI + at least 1 other gate → ALERT (sends Telegram with cooldown)
    if ai_fired and (ueba_fired or suricata_fired or abuse_score >= BLOCK_THRESHOLD):
        reasons = [f"AI({ai_score:.3f})"]
        if ueba_fired:                       reasons.append("UEBA")
        if suricata_fired:                   reasons.append("Suricata")
        if abuse_score >= BLOCK_THRESHOLD:   reasons.append(f"AbuseIPDB({abuse_score})")
        return "ALERT", " + ".join(reasons)

    # Gate 4 — single non-AI gate → log to DB only, no Telegram
    if ueba_fired or suricata_fired:
        reasons = []
        if ueba_fired:     reasons.append("UEBA")
        if suricata_fired: reasons.append("Suricata")
        return "LOG_ONLY", " + ".join(reasons)

    # Gate 5 — very high AbuseIPDB alone
    if abuse_score >= 80:
        return "ALERT", f"Known bad IP: AbuseIPDB({abuse_score})"

    return "NORMAL", ""

def execute_action(src_ip, action, reason, event):
    if action == "NORMAL":
        return

    ai_score       = float(event.get("ai_score", 1.0))
    abuse_score    = int(r.get(f"intel:{src_ip}:abuseipdb") or 0)
    suricata_fired = bool(event.get("suricata_fired", False)) or r.exists(f"suricata:recent:{src_ip}") == 1
    ueba_fired     = bool(event.get("ueba_fired", False))     or r.exists(f"ueba:alert:{src_ip}") == 1
    honeypot_fired = bool(event.get("honeypot_fired", False)) or r.exists(f"honeypot:hit:{src_ip}") == 1
    shap           = event.get("shap_top5", {})

    log.warning(f"⚡ SOAR: {action} | {src_ip} | {reason}")

    telegram_sent    = False
    firewall_blocked = False

    # LOG_ONLY — write to DB silently, no Telegram
    if action == "LOG_ONLY":
        log_soar_action(src_ip, action, reason, ai_score, abuse_score,
                        suricata_fired, ueba_fired, honeypot_fired, False, False)
        return

    # Rate limit Telegram per IP per action type
    cooldown = TG_COOLDOWN.get(action, 1800)
    tg_key   = f"soar:tg:{src_ip}:{action}"
    if r.exists(tg_key):
        log.info(f"⏸️ Telegram suppressed: {src_ip} {action} (cooldown)")
    else:
        emoji = {"ALERT":"⚠️","SOFT_BLOCK":"🔴","BLOCK":"🚫","EMERGENCY_BLOCK":"🆘"}.get(action,"ℹ️")
        shap_text = ""
        if shap:
            shap_text = "\n*Top features:*\n" + "\n".join(f"  `{k}`: {v}" for k,v in list(shap.items())[:3])
        msg = (
            f"{emoji} *Mobilis SOC*\n"
            f"*Action:* `{action}`\n"
            f"*IP:* `{src_ip}`\n"
            f"*Reason:* {reason}\n"
            f"*AI Score:* `{ai_score:.4f}`\n"
            f"*AbuseIPDB:* `{abuse_score}/100`\n"
            f"*Gates:* {'Suricata ' if suricata_fired else ''}{'UEBA ' if ueba_fired else ''}{'Honeypot ' if honeypot_fired else ''}"
            f"{shap_text}\n"
            f"*Time:* {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}"
        )
        telegram_sent = send_telegram(msg)
        if telegram_sent:
            r.setex(tg_key, cooldown, "1")

    log_soar_action(src_ip, action, reason, ai_score, abuse_score,
                    suricata_fired, ueba_fired, honeypot_fired,
                    telegram_sent, firewall_blocked)

    if action in ("BLOCK", "EMERGENCY_BLOCK"):
        log_blocked_ip(src_ip, "HARD", reason)
        r.setex(f"soar:blocked:{src_ip}", 86400, "HARD")
    elif action == "SOFT_BLOCK":
        log_blocked_ip(src_ip, "SOFT", reason, SOFT_BLOCK_MIN)
        r.setex(f"soar:blocked:{src_ip}", SOFT_BLOCK_MIN * 60, "SOFT")

def main():
    log.info("🚀 SOAR Engine V2 starting...")
    r.ping()
    log.info("✅ Redis connected")
    log.info(f"✅ Telegram: {'configured' if TELEGRAM_TOKEN else 'NOT configured'}")

    conf = {
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id"         : "soar-engine-v2",
        "auto.offset.reset": "latest",
    }
    consumer = Consumer(conf)
    consumer.subscribe(["soar-actions", "honeypot-alerts", "suricata-alerts"])
    log.info("✅ Subscribed to soar-actions, honeypot-alerts, suricata-alerts")

    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None or msg.error():
                continue
            try:
                event = json.loads(msg.value().decode())
                topic = msg.topic()

                if topic == "honeypot-alerts":
                    event["honeypot_fired"] = True
                    event["ai_score"]       = -1.0
                elif topic == "suricata-alerts":
                    event["suricata_fired"] = True
                    event["ai_score"]       = event.get("ai_score", 0.0)

                src_ip = event.get("src_ip", "").strip()
                if not src_ip:
                    continue

                if r.exists(f"soar:blocked:{src_ip}"):
                    continue

                action, reason = decide(event)
                execute_action(src_ip, action, reason, event)

            except Exception as e:
                log.error(f"SOAR error: {e}")
    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()

if __name__ == "__main__":
    main()
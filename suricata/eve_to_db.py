import json
import time
import logging
import os
import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("Suricata-DB-Writer")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://mobilis_admin:Mob1l1s%40SOC2025@postgres:5432/mobilis_soc")
EVE_LOG      = os.getenv("EVE_LOG", "/var/log/suricata/eve.json")

def db_insert(alert):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO suricata_alerts
            (src_ip, dst_ip, dst_port, protocol, rule_id, signature, severity, category, raw_alert)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            alert.get("src_ip"),
            alert.get("dst_ip"),
            alert.get("dst_port"),
            alert.get("protocol"),
            alert.get("rule_id"),
            alert.get("signature"),
            alert.get("severity"),
            alert.get("category", ""),
            json.dumps(alert.get("raw", {}))
        ))
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        log.error(f"DB error: {e}")

def tail_eve(filepath):
    while not os.path.exists(filepath):
        log.info(f"Waiting for EVE log: {filepath}")
        time.sleep(3)
    log.info(f"✅ Tailing: {filepath}")
    with open(filepath, "r") as f:
        f.seek(0, 2)
        while True:
            try:
                line = f.readline()
                if not line:
                    time.sleep(0.1)
                    continue
                yield line.strip()
            except OSError:
                log.warning("EVE log rotated — reopening...")
                time.sleep(1)
                break

def main():
    log.info("🚀 Suricata → DB writer starting...")
    while True:
        for line in tail_eve(EVE_LOG):
            try:
                event = json.loads(line)
                if event.get("event_type") != "alert":
                    continue
                alert_data = event.get("alert", {})
                alert = {
                    "src_ip"   : event.get("src_ip"),
                    "dst_ip"   : event.get("dest_ip"),
                    "dst_port" : event.get("dest_port"),
                    "protocol" : event.get("proto"),
                    "rule_id"  : alert_data.get("signature_id"),
                    "signature": alert_data.get("signature"),
                    "severity" : alert_data.get("severity"),
                    "category" : alert_data.get("category", ""),
                    "raw"      : event,
                }
                db_insert(alert)
                log.warning(f"🚨 Suricata → DB | {alert['src_ip']} → {alert['dst_ip']}:{alert['dst_port']} | {alert['signature']}")
            except Exception as e:
                log.error(f"Parse error: {e}")

if __name__ == "__main__":
    main()

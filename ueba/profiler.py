import json
import logging
import os
import time
import redis
from confluent_kafka import Consumer, Producer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("Mobilis-UEBA-V4")

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:29092")
REDIS_HOST      = os.getenv("REDIS_HOST",       "redis")
REDIS_PORT      = int(os.getenv("REDIS_PORT",   "6379"))
REDIS_PASSWORD  = os.getenv("REDIS_PASSWORD",   "R3d1s@SOC2025")
TTL_24H         = 86400
TTL_10MIN       = 600
TTL_7DAYS       = 604800

# Never alert on these IPs
WHITELIST = {
    "192.168.100.1", "192.168.8.1", "192.168.0.1",
    "224.0.0.251", "224.0.0.252", "239.255.255.250",
    "255.255.255.255"
}

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT,
                password=REDIS_PASSWORD, decode_responses=True)
producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})

def delivery_report(err, msg):
    if err:
        log.error(f"❌ Kafka delivery failed: {err}")

def fire_ueba_alert(src_ip, alert_type, description, baseline, observed, severity="WARNING"):
    payload = {
        "timestamp"     : time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "src_ip"        : src_ip,
        "alert_type"    : alert_type,
        "description"   : description,
        "baseline_value": baseline,
        "observed_value": observed,
        "severity"      : severity,
    }
    producer.produce("ueba-alerts", json.dumps(payload).encode("utf-8"), callback=delivery_report)
    producer.poll(0)
    r.setex(f"ueba:alert:{src_ip}", TTL_10MIN, severity)
    log.warning(f"🔍 UEBA {severity} | {src_ip} | {alert_type} | {description}")

def update_profile(src_ip, dst_ip, dst_port, hour, pkt_size):
    base = f"ueba:{src_ip}"

    ports_key = f"{base}:ports"
    is_new_port = r.sismember(ports_key, dst_port) == 0
    r.sadd(ports_key, dst_port)
    r.expire(ports_key, TTL_24H)

    dsts_key = f"{base}:dsts"
    is_new_dst = r.sismember(dsts_key, dst_ip) == 0
    r.sadd(dsts_key, dst_ip)
    r.expire(dsts_key, TTL_24H)

    hours_key = f"{base}:hours"
    r.zincrby(hours_key, 1, str(hour))
    r.expire(hours_key, TTL_24H)

    seen_key = f"{base}:first_seen"
    is_new_ip = not r.exists(seen_key)
    if is_new_ip:
        r.set(seen_key, time.time(), ex=TTL_7DAYS)

    return {"is_new_ip": is_new_ip, "is_new_dst": is_new_dst, "is_new_port": is_new_port}

def check_hour_anomaly(src_ip, hour):
    all_hours = r.zrange(f"ueba:{src_ip}:hours", 0, -1)
    # Need at least 5 hours of history and this hour must be totally new
    return len(all_hours) >= 5 and str(hour) not in all_hours

def process_flow(raw: dict):
    src_ip   = str(raw.get("Source IP",        raw.get("src_ip",   ""))).strip()
    dst_ip   = str(raw.get("Destination IP",   raw.get("dst_ip",   ""))).strip()
    dst_port = str(raw.get("Destination Port", raw.get("dst_port",""))).strip()
    pkt_size = float(raw.get("Average Packet Size", raw.get("pkt_size_avg", 0)) or 0)

    flow_pkts_s = float(raw.get("Flow Packets/s",       raw.get("flow_pkts_s", 0)) or 0)
    tot_fwd     = float(raw.get("Total Fwd Packets",    raw.get("tot_fwd_pkts", 0)) or 0)
    tot_bwd     = float(raw.get("Total Backward Packets",raw.get("tot_bwd_pkts", 0)) or 0)
    flow_dur    = float(raw.get("Flow Duration",        raw.get("flow_duration", 1)) or 1)

    if not src_ip or src_ip in WHITELIST:
        return
    if src_ip.startswith("224.") or src_ip.startswith("239.") or src_ip.endswith(".255"):
        return

    hour  = time.gmtime().tm_hour
    flags = update_profile(src_ip, dst_ip, dst_port, hour, pkt_size)

    # ── RULE 1: Port scan — one-sided fast flows ───────────────
    # Only fires after seeing 5+ suspicious flows in 60 seconds
    if (tot_fwd >= 3 and tot_bwd == 0 and flow_pkts_s > 100 and flow_dur < 1000000):
        scan_key = f"ueba:{src_ip}:scan_flows"
        r.incr(scan_key)
        r.expire(scan_key, 60)
        scan_count = int(r.get(scan_key) or 0)
        if scan_count >= 5:
            fire_ueba_alert(
                src_ip      = src_ip,
                alert_type  = "PORT_SCAN",
                description = f"One-sided fast flows: {scan_count} in 60s | pkts/s:{flow_pkts_s:.0f}",
                baseline    = "Bidirectional flows with bwd packets",
                observed    = f"{scan_count} one-sided flows in 60s",
                severity    = "CRITICAL"
            )
            r.setex(f"ueba:alert:{src_ip}", TTL_10MIN, "CRITICAL")
            r.delete(scan_key)
            return

    # ── RULE 2: Port count threshold ───────────────────────────
    port_count = r.scard(f"ueba:{src_ip}:ports")
    if port_count > 50:
        fire_ueba_alert(
            src_ip      = src_ip,
            alert_type  = "PORT_SCAN",
            description = f"Contacted {port_count} unique ports in 24h",
            baseline    = "< 50 unique ports per day",
            observed    = f"{port_count} unique ports",
            severity    = "CRITICAL"
        )
        r.setex(f"ueba:alert:{src_ip}", TTL_10MIN, "CRITICAL")
        r.delete(f"ueba:{src_ip}:ports")
        return

    # ── RULE 3: HTTP flood ─────────────────────────────────────
    if dst_port == "80" and flow_pkts_s > 200:
        fire_ueba_alert(
            src_ip      = src_ip,
            alert_type  = "HTTP_FLOOD",
            description = f"High-rate HTTP: {flow_pkts_s:.0f} pkts/s to port 80",
            baseline    = "< 50 pkts/s to port 80",
            observed    = f"{flow_pkts_s:.0f} pkts/s",
            severity    = "CRITICAL"
        )
        r.setex(f"ueba:alert:{src_ip}", TTL_10MIN, "CRITICAL")
        return

    # ── RULE 4: New destination — ONLY after 7 days of history ─
    # This prevents day-1 spam where every destination is "new"
    seen_key    = f"ueba:{src_ip}:first_seen"
    first_seen  = r.get(seen_key)
    profile_age = time.time() - float(first_seen) if first_seen else 0

    if (flags["is_new_dst"]
            and not flags["is_new_ip"]
            and profile_age > TTL_7DAYS          # 7 days warmup
            and not dst_ip.startswith("192.168.")
            and not dst_ip.startswith("10.")
            and not dst_ip.startswith("172.")):
        fire_ueba_alert(
            src_ip      = src_ip,
            alert_type  = "NEW_DESTINATION",
            description = f"First time connecting to {dst_ip}:{dst_port}",
            baseline    = "Never seen in 7-day profile",
            observed    = f"{dst_ip}:{dst_port}",
            severity    = "WARNING"
        )

    # ── RULE 5: Unusual hour — needs 5+ hours of history ───────
    # Disabled for first 3 days to avoid startup noise
    if profile_age > 259200:   # 3 days
        if check_hour_anomaly(src_ip, hour):
            fire_ueba_alert(
                src_ip      = src_ip,
                alert_type  = "UNUSUAL_HOUR",
                description = f"Active at {hour:02d}:00 UTC — never seen before",
                baseline    = "Known active hours from profile",
                observed    = f"Hour {hour:02d}:00 UTC",
                severity    = "WARNING"
            )

def main():
    log.info("🚀 UEBA Profiler V4 starting...")
    try:
        r.ping()
        log.info("✅ Redis connected")
    except Exception as e:
        log.critical(f"❌ Redis failed: {e}")
        return

    conf = {
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id"         : "ueba-profiler-v4",
        "auto.offset.reset": "latest",
    }
    consumer = Consumer(conf)
    consumer.subscribe(["network-traffic"])
    log.info("✅ Subscribed to network-traffic")

    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None or msg.error():
                continue
            try:
                raw = json.loads(msg.value().decode("utf-8"))
                process_flow(raw)
            except Exception as e:
                log.error(f"Flow error: {e}")
    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()
        producer.flush()

if __name__ == "__main__":
    main()
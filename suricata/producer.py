import json
import time
import logging
import os
from confluent_kafka import Producer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("Mobilis-Suricata-Producer")

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:29092")
EVE_LOG         = os.getenv("EVE_LOG", "/var/log/suricata/eve.json")
KAFKA_TOPIC     = "suricata-alerts"

producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})

def delivery_report(err, msg):
    if err:
        log.error(f"❌ Kafka delivery failed: {err}")

def tail_eve(filepath):
    """Follow the EVE JSON log file like `tail -f`."""
    while not os.path.exists(filepath):
        log.info(f"Waiting for EVE log: {filepath}")
        time.sleep(3)

    log.info(f"✅ Tailing: {filepath}")
    with open(filepath, "r") as f:
        f.seek(0, 2)  # jump to end
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.1)
                continue
            yield line.strip()

def main():
    log.info("🚀 Suricata EVE → Kafka producer starting...")

    for line in tail_eve(EVE_LOG):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Only forward alert events
        if event.get("event_type") != "alert":
            continue

        alert = event.get("alert", {})
        payload = {
            "timestamp"  : event.get("timestamp"),
            "src_ip"     : event.get("src_ip"),
            "src_port"   : event.get("src_port"),
            "dst_ip"     : event.get("dest_ip"),
            "dst_port"   : event.get("dest_port"),
            "protocol"   : event.get("proto"),
            "rule_id"    : alert.get("signature_id"),
            "signature"  : alert.get("signature"),
            "category"   : alert.get("category"),
            "severity"   : alert.get("severity"),
            "community_id": event.get("community_id"),
            "raw"        : event,
        }

        producer.produce(
            KAFKA_TOPIC,
            json.dumps(payload).encode("utf-8"),
            callback=delivery_report
        )
        producer.poll(0)

        log.warning(
            f"🚨 Suricata ALERT | {payload['src_ip']} → {payload['dst_ip']}:{payload['dst_port']} "
            f"| {payload['signature']} | severity={payload['severity']}"
        )

if __name__ == "__main__":
    main()

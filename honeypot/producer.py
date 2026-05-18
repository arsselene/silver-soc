import json
import time
import logging
import os
from confluent_kafka import Producer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("Mobilis-Honeypot-Producer")

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:29092")
COWRIE_LOG      = os.getenv("COWRIE_LOG", "/cowrie/var/log/cowrie/cowrie.json")
KAFKA_TOPIC     = "honeypot-alerts"

producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})

def delivery_report(err, msg):
    if err:
        log.error(f"❌ Kafka delivery failed: {err}")

# Events we care about — anything else is noise
INTERESTING_EVENTS = {
    "cowrie.login.success",
    "cowrie.login.failed",
    "cowrie.command.input",
    "cowrie.session.connect",
    "cowrie.session.file_download",
    "cowrie.session.file_upload",
    "cowrie.direct-tcpip.request",
    "cowrie.session.closed",
}

def tail_log(filepath):
    while not os.path.exists(filepath):
        log.info(f"Waiting for Cowrie log: {filepath}")
        time.sleep(3)
    log.info(f"✅ Tailing honeypot log: {filepath}")
    with open(filepath, "r") as f:
        f.seek(0, 2)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.1)
                continue
            yield line.strip()

def main():
    log.info("🍯 Honeypot alert producer starting...")

    for line in tail_log(COWRIE_LOG):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_id = event.get("eventid", "")
        if event_id not in INTERESTING_EVENTS:
            continue

        payload = {
            "timestamp"  : event.get("timestamp"),
            "src_ip"     : event.get("src_ip"),
            "src_port"   : event.get("src_port"),
            "dst_ip"     : event.get("dst_ip"),
            "dst_port"   : event.get("dst_port"),
            "event_type" : event_id,
            "username"   : event.get("username"),
            "password"   : event.get("password"),
            "command"    : event.get("input"),
            "url"        : event.get("url"),
            "session"    : event.get("session"),
            "sensor"     : event.get("sensor"),
            "severity"   : "CRITICAL",
            "auto_block" : True,
            "raw"        : event,
        }

        producer.produce(
            KAFKA_TOPIC,
            json.dumps(payload, default=str).encode("utf-8"),
            callback=delivery_report
        )
        producer.poll(0)

        log.critical(
            f"🍯 HONEYPOT HIT | {payload['src_ip']} | "
            f"{event_id} | user={payload['username']} | "
            f"cmd={payload['command']}"
        )

if __name__ == "__main__":
    main()

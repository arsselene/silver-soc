import json
import sys
import time
import logging
import signal
from confluent_kafka import Producer
from cicflowmeter.sniffer import create_sniffer

# ── LOGGING ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("Mobilis-Sensor")

# ── CONFIG ───────────────────────────────────────────────────
INTERFACE      = "WiFi"
KAFKA_SERVER   = "localhost:9092"
KAFKA_TOPIC    = "network-traffic"

# Keys CICFlowMeter outputs → model feature names
SCHEMA_MAP = {
    "flow_duration"       : "Flow Duration",
    "tot_fwd_pkts"        : "Total Fwd Packets",
    "tot_bwd_pkts"        : "Total Backward Packets",
    "totlen_fwd_pkts"     : "Total Length of Fwd Packets",
    "totlen_bwd_pkts"     : "Total Length of Bwd Packets",
    "fwd_pkt_len_max"     : "Fwd Packet Length Max",
    "fwd_pkt_len_min"     : "Fwd Packet Length Min",
    "fwd_pkt_len_mean"    : "Fwd Packet Length Mean",
    "fwd_pkt_len_std"     : "Fwd Packet Length Std",
    "bwd_pkt_len_max"     : "Bwd Packet Length Max",
    "bwd_pkt_len_min"     : "Bwd Packet Length Min",
    "bwd_pkt_len_mean"    : "Bwd Packet Length Mean",
    "bwd_pkt_len_std"     : "Bwd Packet Length Std",
    "flow_byts_s"         : "Flow Bytes/s",
    "flow_pkts_s"         : "Flow Packets/s",
    "flow_iat_mean"       : "Flow IAT Mean",
    "flow_iat_std"        : "Flow IAT Std",
    "flow_iat_max"        : "Flow IAT Max",
    "flow_iat_min"        : "Flow IAT Min",
    "fwd_iat_tot"         : "Fwd IAT Total",
    "fwd_iat_mean"        : "Fwd IAT Mean",
    "fwd_iat_std"         : "Fwd IAT Std",
    "fwd_iat_max"         : "Fwd IAT Max",
    "fwd_iat_min"         : "Fwd IAT Min",
    "bwd_iat_tot"         : "Bwd IAT Total",
    "bwd_iat_mean"        : "Bwd IAT Mean",
    "bwd_iat_std"         : "Bwd IAT Std",
    "bwd_iat_max"         : "Bwd IAT Max",
    "bwd_iat_min"         : "Bwd IAT Min",
    "fwd_psh_flags"       : "Fwd PSH Flags",
    "bwd_psh_flags"       : "Bwd PSH Flags",
    "fwd_urg_flags"       : "Fwd URG Flags",
    "bwd_urg_flags"       : "Bwd URG Flags",
    "fwd_header_len"      : "Fwd Header Length",
    "bwd_header_len"      : "Bwd Header Length",
    "fwd_pkts_s"          : "Fwd Packets/s",
    "bwd_pkts_s"          : "Bwd Packets/s",
    "pkt_len_min"         : "Min Packet Length",
    "pkt_len_max"         : "Max Packet Length",
    "pkt_len_mean"        : "Packet Length Mean",
    "pkt_len_std"         : "Packet Length Std",
    "pkt_len_var"         : "Packet Length Variance",
    "fin_flag_cnt"        : "FIN Flag Count",
    "syn_flag_cnt"        : "SYN Flag Count",
    "rst_flag_cnt"        : "RST Flag Count",
    "psh_flag_cnt"        : "PSH Flag Count",
    "ack_flag_cnt"        : "ACK Flag Count",
    "urg_flag_cnt"        : "URG Flag Count",
    "cwe_flag_count"      : "CWE Flag Count",
    "ece_flag_cnt"        : "ECE Flag Count",
    "down_up_ratio"       : "Down/Up Ratio",
    "pkt_size_avg"        : "Average Packet Size",
    "fwd_seg_size_avg"    : "Avg Fwd Segment Size",
    "bwd_seg_size_avg"    : "Avg Bwd Segment Size",
    "fwd_byt_blk_avg"     : "Fwd Avg Bytes/Bulk",
    "fwd_pkt_blk_avg"     : "Fwd Avg Packets/Bulk",
    "fwd_blk_rate_avg"    : "Fwd Avg Bulk Rate",
    "bwd_byt_blk_avg"     : "Bwd Avg Bytes/Bulk",
    "bwd_pkt_blk_avg"     : "Bwd Avg Packets/Bulk",
    "bwd_blk_rate_avg"    : "Bwd Avg Bulk Rate",
    "subflow_fwd_pkts"    : "Subflow Fwd Packets",
    "subflow_fwd_byts"    : "Subflow Fwd Bytes",
    "subflow_bwd_pkts"    : "Subflow Bwd Packets",
    "subflow_bwd_byts"    : "Subflow Bwd Bytes",
    "init_fwd_win_byts"   : "Init_Win_bytes_forward",
    "init_bwd_win_byts"   : "Init_Win_bytes_backward",
    "act_data_pkt_fwd"    : "act_data_pkt_fwd",
    "min_seg_size_forward": "min_seg_size_forward",
    "active_mean"         : "Active Mean",
    "active_std"          : "Active Std",
    "active_max"          : "Active Max",
    "active_min"          : "Active Min",
    "idle_mean"           : "Idle Mean",
    "idle_std"            : "Idle Std",
    "idle_max"            : "Idle Max",
    "idle_min"            : "Idle Min",
}

# ── KAFKA PRODUCER ────────────────────────────────────────────
try:
    producer = Producer({
        "bootstrap.servers": KAFKA_SERVER,
        "queue.buffering.max.ms": 100,
        "queue.buffering.max.messages": 100000,
    })
    producer.list_topics(timeout=5)
    log.info(f"✅ Kafka connected at {KAFKA_SERVER}")
except Exception as e:
    log.critical(f"❌ Kafka connection failed: {e}")
    sys.exit(1)

def delivery_report(err, msg):
    if err is not None:
        log.error(f"❌ Kafka delivery failed: {err}")

# ── KAFKA INTERCEPTOR ─────────────────────────────────────────
class KafkaInterceptor:
    _headers = None

    def write(self, data):
        if isinstance(data, dict):
            self._send(data)

    def writerow(self, row):
        if isinstance(row, dict):
            self._send(row)
        elif isinstance(row, list):
            if self._headers is None:
                self._headers = row
            else:
                self._send(dict(zip(self._headers, row)))

    def _send(self, raw: dict):
        # Translate snake_case keys → human-readable keys the AI engine expects
        translated = {}
        for key, value in raw.items():
            if key is not None:
                clean = str(key).strip()
                translated[SCHEMA_MAP.get(clean, clean)] = value

        # Keep original src/dst metadata
        translated["Source IP"]        = translated.get("Source IP",        raw.get("src_ip",   ""))
        translated["Destination IP"]   = translated.get("Destination IP",   raw.get("dst_ip",   ""))
        translated["Destination Port"] = translated.get("Destination Port", raw.get("dst_port", ""))
        translated["Protocol"]         = translated.get("Protocol",         raw.get("protocol", ""))

        try:
            producer.produce(
                KAFKA_TOPIC,
                json.dumps(translated, default=str).encode("utf-8"),
                callback=delivery_report
            )
            producer.poll(0)
        except BufferError:
            log.warning("⚠️  Kafka buffer full — flushing...")
            producer.flush(timeout=5)
            producer.produce(KAFKA_TOPIC, json.dumps(translated, default=str).encode("utf-8"))

        src  = translated.get("Source IP", "?")
        dst  = translated.get("Destination IP", "?")
        port = translated.get("Destination Port", "?")
        log.info(f"📡 Flow → Kafka | {src} → {dst}:{port}")

    def close(self):
        log.info("🔄 Flushing Kafka queue...")
        producer.flush(timeout=10)
        log.info("✅ Done.")

# ── HIJACK HELPER ─────────────────────────────────────────────
def hijack_sniffer(result, interceptor):
    candidates = []
    if isinstance(result, tuple):
        candidates.extend([r for r in result if r is not None])
    else:
        candidates.append(result)
        for attr in ("session", "_session", "flow_session"):
            inner = getattr(result, attr, None)
            if inner:
                candidates.append(inner)

    for obj in candidates:
        for attr in ("output_writer", "output", "_output", "writer", "csv_writer"):
            if hasattr(obj, attr):
                setattr(obj, attr, interceptor)
                log.info(f"✅ Hijack OK: {type(obj).__name__}.{attr}")
                return True

    log.error("❌ Hijack FAILED — could not find output writer")
    return False

# ── MAIN ──────────────────────────────────────────────────────
interceptor = KafkaInterceptor()

log.info(f"🚀 Mobilis Sensor V2 starting on interface: {INTERFACE}")
log.info("Listening for completed flows (TCP FIN / 120s timeout)...")

try:
    result = create_sniffer(
        input_file=None,
        input_interface=INTERFACE,
        output_mode="csv",
        output="dummy.csv",
    )
except Exception as e:
    log.critical(f"❌ create_sniffer() failed: {e}")
    sys.exit(1)

hijack_sniffer(result, interceptor)

sniffer = result[0] if isinstance(result, tuple) else result

def shutdown(sig, frame):
    log.info("\n🛑 Shutting down sensor...")
    try:
        sniffer.stop()
    except Exception:
        pass
    interceptor.close()
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

try:
    sniffer.start()
    log.info("✅ Sniffer running. Waiting for flows...")
    sniffer.join()
except Exception as e:
    log.critical(f"❌ Sniffer crashed: {e}", exc_info=True)
    interceptor.close()
    sys.exit(1)
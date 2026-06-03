import json, logging, os, threading, traceback
import numpy as np
import pandas as pd
import joblib, shap, redis, psycopg2
from confluent_kafka import Consumer, Producer
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("Silver-AI")

KAFKA_BOOTSTRAP      = os.getenv("KAFKA_BOOTSTRAP",      "kafka:29092")
DATABASE_URL         = os.getenv("DATABASE_URL",          "postgresql://mobilis_admin:Mob1l1s%40SOC2025@postgres:5432/mobilis_soc")
REDIS_HOST           = os.getenv("REDIS_HOST",            "redis")
REDIS_PORT           = int(os.getenv("REDIS_PORT",        "6379"))
REDIS_PASSWORD       = os.getenv("REDIS_PASSWORD",        "R3d1s@SOC2025")
AI_THRESHOLD_NORMAL  = float(os.getenv("AI_THRESHOLD_NORMAL",   "0.24"))
AI_THRESHOLD_ZERODAY = float(os.getenv("AI_THRESHOLD_ZERO_DAY", "0.15"))

# ── Kafka key → model feature name mapping ────────────────────
KAFKA_TO_MODEL = {
    "Flow Duration"               : "flow_duration",
    "Flow Bytes/s"                : "flow_byts_s",
    "Flow Packets/s"              : "flow_pkts_s",
    "Fwd Packets/s"               : "fwd_pkts_s",
    "Bwd Packets/s"               : "bwd_pkts_s",
    "Total Fwd Packets"           : "tot_fwd_pkts",
    "Total Backward Packets"      : "tot_bwd_pkts",
    "Total Length of Fwd Packets" : "totlen_fwd_pkts",
    "Total Length of Bwd Packets" : "totlen_bwd_pkts",
    "Fwd Packet Length Max"       : "fwd_pkt_len_max",
    "Fwd Packet Length Min"       : "fwd_pkt_len_min",
    "Fwd Packet Length Mean"      : "fwd_pkt_len_mean",
    "Fwd Packet Length Std"       : "fwd_pkt_len_std",
    "Bwd Packet Length Max"       : "bwd_pkt_len_max",
    "Bwd Packet Length Min"       : "bwd_pkt_len_min",
    "Bwd Packet Length Mean"      : "bwd_pkt_len_mean",
    "Bwd Packet Length Std"       : "bwd_pkt_len_std",
    "Max Packet Length"           : "pkt_len_max",
    "Min Packet Length"           : "pkt_len_min",
    "Packet Length Mean"          : "pkt_len_mean",
    "Packet Length Std"           : "pkt_len_std",
    "Packet Length Variance"      : "pkt_len_var",
    "Fwd Header Length"           : "fwd_header_len",
    "Bwd Header Length"           : "bwd_header_len",
    "fwd_seg_size_min"            : "fwd_seg_size_min",
    "fwd_act_data_pkts"           : "fwd_act_data_pkts",
    "Flow IAT Mean"               : "flow_iat_mean",
    "Flow IAT Max"                : "flow_iat_max",
    "Flow IAT Min"                : "flow_iat_min",
    "Flow IAT Std"                : "flow_iat_std",
    "Fwd IAT Total"               : "fwd_iat_tot",
    "Fwd IAT Max"                 : "fwd_iat_max",
    "Fwd IAT Min"                 : "fwd_iat_min",
    "Fwd IAT Mean"                : "fwd_iat_mean",
    "Fwd IAT Std"                 : "fwd_iat_std",
    "Bwd IAT Total"               : "bwd_iat_tot",
    "Bwd IAT Max"                 : "bwd_iat_max",
    "Bwd IAT Min"                 : "bwd_iat_min",
    "Bwd IAT Mean"                : "bwd_iat_mean",
    "Bwd IAT Std"                 : "bwd_iat_std",
    "Fwd PSH Flags"               : "fwd_psh_flags",
    "Bwd PSH Flags"               : "bwd_psh_flags",
    "Fwd URG Flags"               : "fwd_urg_flags",
    "Bwd URG Flags"               : "bwd_urg_flags",
    "FIN Flag Count"              : "fin_flag_cnt",
    "SYN Flag Count"              : "syn_flag_cnt",
    "RST Flag Count"              : "rst_flag_cnt",
    "PSH Flag Count"              : "psh_flag_cnt",
    "ACK Flag Count"              : "ack_flag_cnt",
    "URG Flag Count"              : "urg_flag_cnt",
    "ECE Flag Count"              : "ece_flag_cnt",
    "Down/Up Ratio"               : "down_up_ratio",
    "Average Packet Size"         : "pkt_size_avg",
    "Init_Win_bytes_forward"      : "init_fwd_win_byts",
    "Init_Win_bytes_backward"     : "init_bwd_win_byts",
    "Active Max"                  : "active_max",
    "Active Min"                  : "active_min",
    "Active Mean"                 : "active_mean",
    "Active Std"                  : "active_std",
    "Idle Max"                    : "idle_max",
    "Idle Min"                    : "idle_min",
    "Idle Mean"                   : "idle_mean",
    "Idle Std"                    : "idle_std",
    "fwd_byts_b_avg"              : "fwd_byts_b_avg",
    "fwd_pkts_b_avg"              : "fwd_pkts_b_avg",
    "bwd_byts_b_avg"              : "bwd_byts_b_avg",
    "bwd_pkts_b_avg"              : "bwd_pkts_b_avg",
    "Fwd Avg Bulk Rate"           : "fwd_blk_rate_avg",
    "Bwd Avg Bulk Rate"           : "bwd_blk_rate_avg",
    "Avg Fwd Segment Size"        : "fwd_seg_size_avg",
    "Avg Bwd Segment Size"        : "bwd_seg_size_avg",
    "cwr_flag_count"              : "cwr_flag_count",
    "Subflow Fwd Packets"         : "subflow_fwd_pkts",
    "Subflow Bwd Packets"         : "subflow_bwd_pkts",
    "Subflow Fwd Bytes"           : "subflow_fwd_byts",
    "Subflow Bwd Bytes"           : "subflow_bwd_byts",
    "Protocol"                    : "protocol",
    "protocol"                    : "protocol",
}

# ── Load model ────────────────────────────────────────────────
model     = None
scaler    = None
cols      = None
explainer = None

try:
    # In ai_engine/main.py change back to:
    model  = joblib.load("models/mobilis_v4_model.pkl")
    scaler = joblib.load("models/mobilis_v4_scaler.pkl")
    cols   = list(joblib.load("models/mobilis_v4_columns.pkl"))
    explainer = shap.TreeExplainer(model)
    log.info(f"✅ Model loaded. {len(cols)} features. Threshold: {AI_THRESHOLD_NORMAL}")
except Exception as e:
    log.critical(f"❌ Model load failed: {e}")

# ── Redis ─────────────────────────────────────────────────────
r = None
try:
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT,
                    password=REDIS_PASSWORD, decode_responses=True)
    r.ping()
    log.info("✅ Redis connected")
except Exception as e:
    log.error(f"❌ Redis failed: {e}")

soar_producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})

# ── Database helpers ──────────────────────────────────────────
def db_insert(query, params):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur  = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        log.error(f"DB error: {e}")

def init_db():
    db_insert("""CREATE TABLE IF NOT EXISTS predictions (
        id SERIAL PRIMARY KEY,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        src_ip VARCHAR(50), dst_ip VARCHAR(50), dst_port VARCHAR(10),
        protocol VARCHAR(10), prediction VARCHAR(20), severity VARCHAR(10),
        anomaly_score FLOAT, ai_threshold FLOAT,
        shap_top5 JSONB, raw_features JSONB)""", ())
    db_insert("""CREATE TABLE IF NOT EXISTS suricata_alerts (
        id SERIAL PRIMARY KEY,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        src_ip VARCHAR(50), dst_ip VARCHAR(50), dst_port INTEGER,
        protocol VARCHAR(10), rule_id INTEGER, signature TEXT,
        severity INTEGER, category VARCHAR(100), raw_alert JSONB)""", ())
    db_insert("""CREATE TABLE IF NOT EXISTS honeypot_alerts (
        id SERIAL PRIMARY KEY,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        src_ip VARCHAR(50), src_port INTEGER,
        username VARCHAR(100), password VARCHAR(100),
        event_type VARCHAR(50), command TEXT,
        session_id VARCHAR(100), auto_blocked BOOLEAN DEFAULT FALSE)""", ())
    db_insert("""CREATE TABLE IF NOT EXISTS soar_actions (
        id SERIAL PRIMARY KEY,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        src_ip VARCHAR(50), action VARCHAR(50), reason VARCHAR(200),
        ai_score FLOAT, abuseipdb_score INTEGER,
        suricata_fired BOOLEAN, ueba_fired BOOLEAN, honeypot_fired BOOLEAN,
        telegram_sent BOOLEAN DEFAULT FALSE,
        firewall_blocked BOOLEAN DEFAULT FALSE)""", ())
    db_insert("""CREATE TABLE IF NOT EXISTS blocked_ips (
        id SERIAL PRIMARY KEY,
        ip_address VARCHAR(50) UNIQUE,
        blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        block_type VARCHAR(20), reason TEXT,
        auto_unblock_at TIMESTAMP,
        unblocked BOOLEAN DEFAULT FALSE)""", ())
    db_insert("""CREATE TABLE IF NOT EXISTS ueba_alerts (
        id SERIAL PRIMARY KEY,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        src_ip VARCHAR(50), alert_type VARCHAR(50),
        description TEXT, baseline_value TEXT,
        observed_value TEXT, severity VARCHAR(20))""", ())
    log.info("✅ DB tables ready")

# ── SHAP explainability ───────────────────────────────────────
def get_shap_top5(scaled_data):
    try:
        vals = explainer.shap_values(scaled_data)
        if isinstance(vals, list):
            vals = vals[0]
        pairs = sorted(
            zip(cols, vals[0]),
            key=lambda x: abs(x[1]),
            reverse=True
        )[:5]
        return {k: round(float(v), 4) for k, v in pairs}
    except Exception as e:
        log.warning(f"SHAP error: {e}")
        return {}

# ── Gate checking ─────────────────────────────────────────────
def check_gates(src_ip, score):
    gates = {
        "ai_fired"       : score < AI_THRESHOLD_NORMAL,
        "zero_day_ai"    : score < AI_THRESHOLD_ZERODAY,
        "suricata_fired" : False,
        "ueba_fired"     : False,
        "honeypot_fired" : False,
        "abuseipdb_score": 0,
    }
    if r:
        gates["suricata_fired"]  = r.exists(f"suricata:recent:{src_ip}") == 1
        gates["ueba_fired"]      = r.exists(f"ueba:alert:{src_ip}") == 1
        gates["honeypot_fired"]  = r.exists(f"honeypot:hit:{src_ip}") == 1
        score_str = r.get(f"intel:{src_ip}:abuseipdb")
        if score_str:
            gates["abuseipdb_score"] = int(score_str)
    return gates

def decide_action(gates):
    if gates["honeypot_fired"]:
        return "EMERGENCY_BLOCK", "Honeypot hit — zero tolerance"
    if gates["ai_fired"] and gates["abuseipdb_score"] >= 50 and gates["suricata_fired"]:
        return "BLOCK", f"All 3 gates: AI + AbuseIPDB({gates['abuseipdb_score']}) + Suricata"
    if gates["zero_day_ai"] and gates["ueba_fired"]:
        return "SOFT_BLOCK", "Zero-day pattern: extreme AI + UEBA"
    if gates["zero_day_ai"]:
        return "SOFT_BLOCK", f"Extreme AI score"
    if gates["ai_fired"] and (gates["ueba_fired"] or gates["suricata_fired"]):
        return "ALERT", "AI + secondary gate"
    if gates["ai_fired"]:
        return "ALERT", "AI anomaly"
    if gates["ueba_fired"] or gates["suricata_fired"]:
        return "LOG_ONLY", "Single non-AI gate"
    return "NORMAL", ""

# ── Main flow processing ──────────────────────────────────────
def process_flow(raw: dict):
    if model is None or cols is None:
        return

    src_ip   = str(raw.get("Source IP",        raw.get("src_ip",   "Unknown")))
    dst_ip   = str(raw.get("Destination IP",   raw.get("dst_ip",   "Unknown")))
    dst_port = str(raw.get("Destination Port", raw.get("dst_port", "Unknown")))
    protocol = str(raw.get("Protocol",         raw.get("protocol", "Unknown")))

    # Translate Kafka keys → model feature names
    model_data = {}
    for k, v in raw.items():
        target = KAFKA_TO_MODEL.get(k)
        if target:
            model_data[target] = v
        elif k in cols:
            model_data[k] = v

    # Build DataFrame with exactly the expected columns
    df = pd.DataFrame([model_data])
    for col in cols:
        if col not in df.columns:
            df[col] = 0
    df = df[cols]
    df = df.replace([np.inf, -np.inf], 0)
    df = df.apply(pd.to_numeric, errors="coerce").fillna(0)

    nonzero = int((df.iloc[0] != 0).sum())

    # Scale and score
    scaled = scaler.transform(df)
    score  = float(model.decision_function(scaled)[0])

    # SHAP only for attacks
    shap_top5 = {}
    if score < AI_THRESHOLD_NORMAL:
        shap_top5 = get_shap_top5(scaled)

    # Classify
    if score < AI_THRESHOLD_ZERODAY:
        severity, prediction = "CRITICAL", "ATTACK"
    elif score < AI_THRESHOLD_NORMAL:
        severity, prediction = "WARNING", "ATTACK"
    else:
        severity, prediction = "INFO", "NORMAL"

    gates  = check_gates(src_ip, score)
    action, reason = decide_action(gates)

    if prediction == "ATTACK":
        log.warning(
            f"🚨 {severity} | Score:{score:.4f} | {nonzero} features | "
            f"{src_ip}→{dst_ip}:{dst_port} | {action} | SHAP:{shap_top5}"
        )
    else:
        log.info(f"🟢 NORMAL | Score:{score:.4f} | {nonzero} features | {src_ip}→{dst_port}")

    # Store in DB — raw_features for retrainer
    db_insert("""
        INSERT INTO predictions
        (src_ip,dst_ip,dst_port,protocol,prediction,severity,
         anomaly_score,ai_threshold,shap_top5,raw_features)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        src_ip, dst_ip, dst_port, protocol, prediction, severity,
        score, AI_THRESHOLD_NORMAL,
        json.dumps(shap_top5),
        json.dumps(df.iloc[0].to_dict())
    ))

    # Publish to SOAR
    if action not in ("NORMAL", "LOG_ONLY"):
        soar_producer.produce("soar-actions", json.dumps({
            "src_ip"        : src_ip,
            "dst_ip"        : dst_ip,
            "dst_port"      : dst_port,
            "action"        : action,
            "reason"        : reason,
            "ai_score"      : score,
            "severity"      : severity,
            "shap_top5"     : shap_top5,
            "suricata_fired": gates["suricata_fired"],
            "ueba_fired"    : gates["ueba_fired"],
            "honeypot_fired": gates["honeypot_fired"],
            "abuseipdb_score": gates["abuseipdb_score"],
        }).encode())
        soar_producer.poll(0)

# ── Kafka consumers ───────────────────────────────────────────
def consume_network():
    conf = {
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id"         : "ai-network-v5",
        "auto.offset.reset": "latest",
    }
    c = Consumer(conf)
    c.subscribe(["network-traffic"])
    log.info("✅ Network consumer started")
    while True:
        try:
            msg = c.poll(1.0)
            if msg is None or msg.error():
                continue
            raw = json.loads(msg.value().decode())
            process_flow(raw)
        except Exception as e:
            log.error(f"Network consumer error: {e}\n{traceback.format_exc()}")

def consume_suricata():
    conf = {
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id"         : "ai-suricata-v5",
        "auto.offset.reset": "latest",
    }
    c = Consumer(conf)
    c.subscribe(["suricata-alerts"])
    while True:
        msg = c.poll(1.0)
        if msg is None or msg.error():
            continue
        try:
            alert  = json.loads(msg.value().decode())
            src_ip = alert.get("src_ip", "")
            if src_ip and r:
                r.setex(f"suricata:recent:{src_ip}", 600, "1")
            db_insert("""
                INSERT INTO suricata_alerts
                (src_ip,dst_ip,dst_port,protocol,rule_id,signature,severity,category,raw_alert)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                src_ip,
                alert.get("dst_ip"),
                alert.get("dst_port"),
                alert.get("protocol"),
                alert.get("rule_id"),
                alert.get("signature"),
                alert.get("severity"),
                alert.get("category", ""),
                json.dumps(alert.get("raw", {}))
            ))
        except Exception as e:
            log.error(f"Suricata consumer error: {e}")

def consume_honeypot():
    conf = {
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id"         : "ai-honeypot-v5",
        "auto.offset.reset": "latest",
    }
    c = Consumer(conf)
    c.subscribe(["honeypot-alerts"])
    while True:
        msg = c.poll(1.0)
        if msg is None or msg.error():
            continue
        try:
            alert  = json.loads(msg.value().decode())
            src_ip = alert.get("src_ip", "")
            if src_ip and r:
                r.setex(f"honeypot:hit:{src_ip}", 86400, "1")
            db_insert("""
                INSERT INTO honeypot_alerts
                (src_ip,src_port,username,password,event_type,command,session_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (
                src_ip,
                alert.get("src_port"),
                alert.get("username"),
                alert.get("password"),
                alert.get("event_type"),
                alert.get("command"),
                alert.get("session")
            ))
        except Exception as e:
            log.error(f"Honeypot consumer error: {e}")

# ── FastAPI app ───────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    for target in [consume_network, consume_suricata, consume_honeypot]:
        threading.Thread(target=target, daemon=True).start()
    log.info("🚀 Silver AI Engine V5 fully started")
    yield

app = FastAPI(title="Silver SOC AI Engine V5", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {
        "status"   : "ok",
        "model"    : model is not None,
        "threshold": AI_THRESHOLD_NORMAL,
        "features" : len(cols) if cols else 0,
    }

@app.get("/stats")
def stats():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur  = conn.cursor()
        cur.execute("SELECT prediction, COUNT(*) FROM predictions GROUP BY prediction")
        rows = cur.fetchall()
        cur.close(); conn.close()
        return {"counts": {r[0]: r[1] for r in rows}}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
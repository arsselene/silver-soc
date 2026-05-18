-- ============================================================
-- MOBILIS SOC V2 — DATABASE SCHEMA
-- Auto-runs on first postgres container boot
-- ============================================================

-- ── NETWORK PREDICTIONS (AI engine output) ─────────────────
CREATE TABLE IF NOT EXISTS predictions (
    id              SERIAL PRIMARY KEY,
    timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    src_ip          VARCHAR(50),
    dst_ip          VARCHAR(50),
    dst_port        VARCHAR(10),
    protocol        VARCHAR(10),
    prediction      VARCHAR(20),   -- NORMAL / ATTACK / ZERO_DAY
    severity        VARCHAR(10),   -- INFO / WARNING / CRITICAL
    anomaly_score   FLOAT,
    ai_threshold    FLOAT,
    shap_top5       JSONB,         -- {feature: shap_value} top 5
    raw_features    JSONB          -- all 77 flow features
);

-- ── SURICATA ALERTS (Layer 1 output) ──────────────────────
CREATE TABLE IF NOT EXISTS suricata_alerts (
    id              SERIAL PRIMARY KEY,
    timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    src_ip          VARCHAR(50),
    dst_ip          VARCHAR(50),
    dst_port        INTEGER,
    protocol        VARCHAR(10),
    rule_id         INTEGER,
    signature       TEXT,
    severity        INTEGER,       -- 1=high 2=medium 3=low
    category        VARCHAR(100),
    raw_alert       JSONB
);

-- ── HONEYPOT ALERTS (Layer 0.5 output) ────────────────────
CREATE TABLE IF NOT EXISTS honeypot_alerts (
    id              SERIAL PRIMARY KEY,
    timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    src_ip          VARCHAR(50),
    src_port        INTEGER,
    username        VARCHAR(100),  -- attempted login username
    password        VARCHAR(100),  -- attempted login password
    event_type      VARCHAR(50),   -- login.attempt / command / download
    command         TEXT,          -- command attacker ran (if any)
    session_id      VARCHAR(100),
    auto_blocked    BOOLEAN DEFAULT FALSE
);

-- ── UEBA ALERTS (Layer 3 output) ──────────────────────────
CREATE TABLE IF NOT EXISTS ueba_alerts (
    id              SERIAL PRIMARY KEY,
    timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    src_ip          VARCHAR(50),
    alert_type      VARCHAR(50),   -- NEW_DESTINATION / GEO_VELOCITY / UNUSUAL_HOUR / PORT_DEVIATION
    description     TEXT,
    baseline_value  VARCHAR(100),  -- what was normal
    observed_value  VARCHAR(100),  -- what was seen
    severity        VARCHAR(10)    -- WARNING / CRITICAL
);

-- ── THREAT INTEL ENRICHMENTS (Layer 4 output) ─────────────
CREATE TABLE IF NOT EXISTS threat_intel (
    id              SERIAL PRIMARY KEY,
    timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ip_address      VARCHAR(50) UNIQUE,
    abuseipdb_score INTEGER,       -- 0-100
    abuseipdb_categories JSONB,    -- attack categories
    otx_pulses      INTEGER,       -- number of OTX threat pulses
    otx_malware     VARCHAR(200),  -- malware family if known
    country         VARCHAR(10),
    isp             VARCHAR(200),
    is_known_bad    BOOLEAN DEFAULT FALSE,
    last_checked    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── SOAR ACTIONS (automated response log) ─────────────────
CREATE TABLE IF NOT EXISTS soar_actions (
    id              SERIAL PRIMARY KEY,
    timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    src_ip          VARCHAR(50),
    action          VARCHAR(50),   -- BLOCK / SOFT_BLOCK / ALERT / EMERGENCY_BLOCK
    reason          VARCHAR(200),  -- which gates triggered
    ai_score        FLOAT,
    abuseipdb_score INTEGER,
    suricata_fired  BOOLEAN,
    ueba_fired      BOOLEAN,
    honeypot_fired  BOOLEAN,
    telegram_sent   BOOLEAN DEFAULT FALSE,
    firewall_blocked BOOLEAN DEFAULT FALSE,
    unblocked_at    TIMESTAMP,     -- for soft-blocks
    notes           TEXT
);

-- ── BLOCKED IPS (active firewall blocks) ──────────────────
CREATE TABLE IF NOT EXISTS blocked_ips (
    id              SERIAL PRIMARY KEY,
    ip_address      VARCHAR(50) UNIQUE,
    blocked_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    block_type      VARCHAR(20),   -- HARD / SOFT
    reason          TEXT,
    auto_unblock_at TIMESTAMP,     -- NULL = permanent
    unblocked       BOOLEAN DEFAULT FALSE
);

-- ── MODEL VERSIONS (retraining log) ───────────────────────
CREATE TABLE IF NOT EXISTS model_versions (
    id              SERIAL PRIMARY KEY,
    trained_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    training_samples INTEGER,
    contamination   FLOAT,
    threshold       FLOAT,
    notes           TEXT,
    active          BOOLEAN DEFAULT FALSE
);

-- ── INDEXES for dashboard query speed ─────────────────────
CREATE INDEX IF NOT EXISTS idx_predictions_timestamp  ON predictions(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_predictions_src_ip     ON predictions(src_ip);
CREATE INDEX IF NOT EXISTS idx_predictions_severity   ON predictions(severity);
CREATE INDEX IF NOT EXISTS idx_suricata_timestamp     ON suricata_alerts(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_honeypot_timestamp     ON honeypot_alerts(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_ueba_timestamp         ON ueba_alerts(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_soar_timestamp         ON soar_actions(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_blocked_ip             ON blocked_ips(ip_address);
CREATE INDEX IF NOT EXISTS idx_intel_ip               ON threat_intel(ip_address);

-- ── SEED: initial model version record ────────────────────
INSERT INTO model_versions (training_samples, contamination, threshold, notes, active)
VALUES (0, 0.027, -0.0500, 'Placeholder — retrain before first use', TRUE)
ON CONFLICT DO NOTHING;
import os
import time
import logging
import joblib
import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extras
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from apscheduler.schedulers.blocking import BlockingScheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("Mobilis-Retrainer")

DATABASE_URL     = os.getenv("DATABASE_URL", "postgresql://mobilis_admin:Mob1l1s%40SOC2025@localhost:5432/mobilis_soc")
MODEL_PATH       = os.getenv("MODEL_PATH",   "C:/Users/mazar/OneDrive/Desktop/mobilis-soc/ai_engine/models")
AI_THRESHOLD     = float(os.getenv("AI_THRESHOLD_NORMAL", "-0.0500"))
MIN_SAMPLES      = int(os.getenv("MIN_SAMPLES", "1000"))
RETRAIN_HOUR     = int(os.getenv("RETRAIN_HOUR", "2"))  # 2am UTC

COLS_FILE  = os.path.join(MODEL_PATH, "mobilis_v4_columns.pkl")
MODEL_FILE = os.path.join(MODEL_PATH, "mobilis_v4_model.pkl")
SCALER_FILE= os.path.join(MODEL_PATH, "mobilis_v4_scaler.pkl")

def load_normal_flows() -> pd.DataFrame:
    """Load last 24h of confirmed-normal flows from PostgreSQL."""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    cur  = conn.cursor()
    cur.execute("""
        SELECT raw_features
        FROM predictions
        WHERE prediction = 'NORMAL'
          AND timestamp > NOW() - INTERVAL '24 hours'
        ORDER BY RANDOM()
        LIMIT 5000
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()

    if not rows:
        return pd.DataFrame()

    records = []
    for row in rows:
        rf = row["raw_features"]
        if isinstance(rf, dict):
            records.append(rf)

    return pd.DataFrame(records)

def retrain():
    log.info("🔄 Auto-retrainer starting...")

    # Load expected columns
    try:
        expected_cols = joblib.load(COLS_FILE)
    except Exception as e:
        log.error(f"❌ Could not load columns: {e}")
        return

    # Load normal flows from DB
    df = load_normal_flows()
    if df.empty or len(df) < MIN_SAMPLES:
        log.warning(f"⚠️  Only {len(df)} normal flows — need {MIN_SAMPLES} minimum. Skipping retrain.")
        return

    log.info(f"📥 Loaded {len(df)} normal flows for retraining")

    # Align columns
    for col in expected_cols:
        if col not in df.columns:
            df[col] = 0
    df = df[expected_cols]
    df = df.replace([np.inf, -np.inf], 0)
    df = df.apply(pd.to_numeric, errors="coerce").fillna(0)

    # Train new scaler and model
    log.info("⚖️  Fitting scaler...")
    scaler = StandardScaler()
    scaled = scaler.fit_transform(df)

    log.info("🧠 Training Isolation Forest...")
    model = IsolationForest(
        n_estimators=100,
        contamination=0.01,
        random_state=42,
        n_jobs=-1
    )
    model.fit(scaled)

    # Quick sanity check — score a sample of the training data
    sample_scores = model.decision_function(scaled[:100])
    mean_score = float(np.mean(sample_scores))
    log.info(f"📊 Sanity check — mean score on training data: {mean_score:.4f}")

    if mean_score < -0.2:
        log.error("❌ Model sanity check failed — mean score too low. Aborting save.")
        return

    # Backup old model
    ts = time.strftime("%Y%m%d_%H%M%S")
    for f, suffix in [(MODEL_FILE, "model"), (SCALER_FILE, "scaler")]:
        backup = f.replace(".pkl", f"_backup_{ts}.pkl")
        try:
            import shutil
            shutil.copy(f, backup)
        except Exception:
            pass

    # Save new model
    joblib.dump(model,  MODEL_FILE)
    joblib.dump(scaler, SCALER_FILE)

    log.info(f"✅ New model saved — trained on {len(df)} flows")
    log.info(f"   Model path: {MODEL_FILE}")
    log.info(f"   Mean score: {mean_score:.4f}")

    # Log to DB
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur  = conn.cursor()
        cur.execute("""
            UPDATE model_versions SET active = FALSE;
            INSERT INTO model_versions
            (training_samples, contamination, threshold, notes, active)
            VALUES (%s, %s, %s, %s, TRUE)
        """, (len(df), 0.01, AI_THRESHOLD,
              f"Auto-retrain at {time.strftime('%Y-%m-%d %H:%M UTC')} — {len(df)} normal flows"))
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        log.error(f"DB log error: {e}")

    log.info("🎉 Retraining complete!")

def run_now():
    """Run immediately on startup for testing."""
    log.info("▶️  Running initial retrain check...")
    retrain()

def main():
    log.info(f"🚀 Auto-retrainer starting — scheduled for {RETRAIN_HOUR:02d}:00 UTC daily")

    # Run once immediately on startup
    run_now()

    # Schedule nightly retraining
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(retrain, "cron", hour=RETRAIN_HOUR, minute=0)

    log.info(f"⏰ Next retrain scheduled for {RETRAIN_HOUR:02d}:00 UTC")
    try:
        scheduler.start()
    except KeyboardInterrupt:
        log.info("🛑 Retrainer stopped")

if __name__ == "__main__":
    main()

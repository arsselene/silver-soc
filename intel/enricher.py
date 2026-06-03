import json
import logging
import os
import time
import requests
import redis
from confluent_kafka import Consumer, Producer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("Mobilis-Intel")

KAFKA_BOOTSTRAP   = os.getenv("KAFKA_BOOTSTRAP",             "kafka:29092")
REDIS_HOST        = os.getenv("REDIS_HOST",                  "redis")
REDIS_PORT        = int(os.getenv("REDIS_PORT",              "6379"))
REDIS_PASSWORD    = os.getenv("REDIS_PASSWORD",              "R3d1s@SOC2025")
ABUSEIPDB_KEY     = os.getenv("ABUSEIPDB_API_KEY",           "")
OTX_KEY           = os.getenv("OTX_API_KEY",                 "")
BLOCK_THRESHOLD   = int(os.getenv("ABUSEIPDB_BLOCK_THRESHOLD","50"))
CACHE_TTL         = 3600

PRIVATE = ("10.","172.16.","172.17.","172.18.","172.19.","172.20.",
           "172.31.","192.168.","127.","0.","::1","224.","239.")

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT,
                password=REDIS_PASSWORD, decode_responses=True)
producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})

def delivery_report(err, msg):
    if err: log.error(f"❌ Kafka: {err}")

def is_private(ip):
    return any(ip.startswith(p) for p in PRIVATE)

# ── GeoIP via ip-api.com (free, no key needed, works for all IPs) ──
def get_geoip(ip):
    key = f"intel:{ip}:geo"
    cached = r.get(key)
    if cached:
        return json.loads(cached)
    try:
        resp = requests.get(
            f"http://ip-api.com/json/{ip}?fields=status,country,countryCode,city,lat,lon,isp,org",
            timeout=5
        )
        if resp.status_code == 200:
            d = resp.json()
            if d.get("status") == "success":
                result = {
                    "lat"         : d.get("lat", 0),
                    "lon"         : d.get("lon", 0),
                    "country"     : d.get("country", ""),
                    "country_code": d.get("countryCode", ""),
                    "city"        : d.get("city", ""),
                    "isp"         : d.get("isp", ""),
                }
                r.setex(key, CACHE_TTL, json.dumps(result))
                # Store lat/lon separately for dashboard GeoIP map
                r.setex(f"intel:{ip}:lat", CACHE_TTL, str(result["lat"]))
                r.setex(f"intel:{ip}:lon", CACHE_TTL, str(result["lon"]))
                r.setex(f"intel:{ip}:country", CACHE_TTL, result["country"])
                r.setex(f"intel:{ip}:city", CACHE_TTL, result["city"])
                r.setex(f"intel:{ip}:isp", CACHE_TTL, result["isp"])
                log.info(f"🌍 GeoIP | {ip} → {result['city']}, {result['country']} "
                         f"({result['lat']},{result['lon']})")
                return result
    except Exception as e:
        log.warning(f"GeoIP error {ip}: {e}")
    return {"lat": 0, "lon": 0, "country": "", "country_code": "", "city": "", "isp": ""}

def check_abuseipdb(ip):
    key = f"intel:{ip}:abuseipdb_full"
    cached = r.get(key)
    if cached:
        return json.loads(cached)
    if not ABUSEIPDB_KEY:
        return {"score": 0, "country": "", "isp": "", "total_reports": 0}
    try:
        resp = requests.get(
            "https://api.abuseipdb.com/api/v2/check",
            headers={"Key": ABUSEIPDB_KEY, "Accept": "application/json"},
            params={"ipAddress": ip, "maxAgeInDays": 90},
            timeout=5
        )
        if resp.status_code == 200:
            d = resp.json().get("data", {})
            result = {
                "score"        : d.get("abuseConfidenceScore", 0),
                "country"      : d.get("countryCode", ""),
                "isp"          : d.get("isp", ""),
                "total_reports": d.get("totalReports", 0),
            }
            r.setex(key, CACHE_TTL, json.dumps(result))
            r.setex(f"intel:{ip}:abuseipdb", CACHE_TTL, str(result["score"]))
            return result
    except Exception as e:
        log.warning(f"AbuseIPDB error {ip}: {e}")
    return {"score": 0, "country": "", "isp": "", "total_reports": 0}

def check_otx(ip):
    key = f"intel:{ip}:otx"
    cached = r.get(key)
    if cached:
        return json.loads(cached)
    if not OTX_KEY:
        return {"pulses": 0, "malware": ""}
    try:
        resp = requests.get(
            f"https://otx.alienvault.com/api/v1/indicators/IPv4/{ip}/general",
            headers={"X-OTX-API-KEY": OTX_KEY},
            timeout=5
        )
        if resp.status_code == 200:
            d    = resp.json()
            info = d.get("pulse_info", {})
            result = {"pulses": info.get("count", 0), "malware": ""}
            r.setex(key, CACHE_TTL, json.dumps(result))
            return result
    except Exception as e:
        log.warning(f"OTX error {ip}: {e}")
    return {"pulses": 0, "malware": ""}

def enrich(ip):
    # Always get GeoIP for ALL IPs including private (for dashboard map)
    geo = get_geoip(ip)

    # Skip AbuseIPDB/OTX for private IPs — they won't have data
    if is_private(ip):
        return None

    if r.exists(f"intel:{ip}:abuseipdb_full"):
        return None  # already cached

    abuse  = check_abuseipdb(ip)
    otx    = check_otx(ip)
    score  = abuse.get("score", 0)
    is_bad = score >= BLOCK_THRESHOLD or otx.get("pulses", 0) > 20

    result = {
        "ip"             : ip,
        "abuseipdb_score": score,
        "country"        : geo.get("country", abuse.get("country", "")),
        "country_code"   : geo.get("country_code", ""),
        "city"           : geo.get("city", ""),
        "lat"            : geo.get("lat", 0),
        "lon"            : geo.get("lon", 0),
        "isp"            : geo.get("isp", abuse.get("isp", "")),
        "total_reports"  : abuse.get("total_reports", 0),
        "otx_pulses"     : otx.get("pulses", 0),
        "is_known_bad"   : is_bad,
        "timestamp"      : time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    if is_bad:
        log.warning(f"🚨 KNOWN BAD | {ip} | Score:{score}/100 | "
                    f"OTX:{otx.get('pulses',0)} | {geo.get('city','')} "
                    f"{geo.get('country','')} | {geo.get('isp','')}")
    else:
        log.info(f"✅ Clean | {ip} | Score:{score}/100 | "
                 f"{geo.get('city','')} {geo.get('country','')} | "
                 f"OTX:{otx.get('pulses',0)}")

    producer.produce("threat-intel", json.dumps(result).encode(),
                     callback=delivery_report)
    producer.poll(0)
    return result

def main():
    log.info("🚀 Threat Intel Enricher V2 starting...")
    r.ping()
    log.info("✅ Redis connected")
    log.info(f"✅ AbuseIPDB: {'loaded' if ABUSEIPDB_KEY else 'MISSING'}")
    log.info(f"✅ OTX: {'loaded' if OTX_KEY else 'MISSING'}")
    log.info("✅ GeoIP: ip-api.com (free, no key required)")

    conf = {"bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": "intel-enricher-v2",
            "auto.offset.reset": "latest"}
    consumer = Consumer(conf)
    consumer.subscribe(["network-traffic", "suricata-alerts", "honeypot-alerts"])
    log.info("✅ Subscribed to 3 topics")

    seen = set()
    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None or msg.error():
                continue
            try:
                raw = json.loads(msg.value().decode())
                for field in ("Source IP","src_ip","Destination IP","dst_ip"):
                    ip = str(raw.get(field, "")).strip()
                    if ip and ip not in seen:
                        enrich(ip)
                        seen.add(ip)
                        if len(seen) > 2000:
                            seen.clear()
            except Exception as e:
                log.error(f"Error: {e}")
    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()
        producer.flush()

if __name__ == "__main__":
    main()
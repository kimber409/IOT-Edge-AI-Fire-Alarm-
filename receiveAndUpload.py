#!/usr/bin/env python3
import time
import requests
import serial

SERIAL_PORT = "/dev/ttyUSB1"
BAUD = 9600

THINGSPEAK_WRITE_KEY = "KEY"
THINGSPEAK_URL = "https://api.thingspeak.com/update"
POST_INTERVAL_SEC = 15

MQ2_WARN = 250
MQ2_DANGER = 400
FLAME_DETECTED_VALUE = 1

def parse_kv_line(line: str):
    line = line.strip()
    if not line:
        return None

    parts = line.split(",")
    kv = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            kv[k.strip()] = v.strip()

    if "tempC" not in kv or "mq2" not in kv or "flame" not in kv:
        return None

    try:
        return {
            "ms": int(kv.get("ms", 0)),
            "tempC": float(kv["tempC"]),
            "mq2": int(float(kv["mq2"])),
            "flame_raw": int(float(kv["flame"])),
            "gas": kv.get("gas", ""),
            "light": kv.get("light", "")
        }
    except Exception:
        return None

def compute_decision(d):
    flameDetected = (d["flame_raw"] == FLAME_DETECTED_VALUE)
    gas_warn = d["mq2"] >= MQ2_WARN
    gas_danger = d["mq2"] >= MQ2_DANGER

    decision = "NORMAL"
    reason = "NORMAL"

    if flameDetected:
        decision = "HIGH_RISK"; reason = "FLAME"
    elif gas_danger:
        decision = "HIGH_RISK"; reason = "MQ2_DANGER"
    elif gas_warn:
        decision = "WARNING"; reason = "MQ2_WARN"

    alarm = (decision == "HIGH_RISK")

    if flameDetected: risk = 1.0
    elif gas_danger: risk = 0.9
    elif gas_warn:   risk = 0.55
    else:            risk = 0.05

    return flameDetected, risk, alarm, decision, reason

def post_to_thingspeak(d, flameDetected, risk, alarm, decision):
    payload = {
        "api_key": THINGSPEAK_WRITE_KEY,
        "field1": d["tempC"],
        "field2": d["mq2"],
        "field3": 1 if flameDetected else 0,
        "field4": round(risk, 3),
        "field5": 1 if alarm else 0,
        "field6": decision,
    }
    r = requests.post(THINGSPEAK_URL, data=payload, timeout=10)
    r.raise_for_status()
    return r.text.strip()

def main():
    print("=== Zigbee → ThingSpeak (live countdown) ===")
    print(f"Serial: {SERIAL_PORT} @ {BAUD}")
    print("CTRL+C to stop\n")

    latest = None
    next_post = time.time() + POST_INTERVAL_SEC
    last_countdown = -1

    with serial.Serial(SERIAL_PORT, BAUD, timeout=0.2) as ser:
        while True:
            # continuously read serial
            raw = ser.readline()
            if raw:
                line = raw.decode("utf-8", errors="replace").strip()
                d = parse_kv_line(line)
                if d:
                    latest = d

            now = time.time()
            remaining = int(next_post - now)

            # show countdown once per second
            if remaining != last_countdown and remaining >= 0:
                print(f"Next upload in: {remaining}s")
                last_countdown = remaining

            if now >= next_post:
                if latest:
                    flameDetected, risk, alarm, decision, reason = compute_decision(latest)
                    print(
                        f"[POSTING] temp={latest['tempC']:.1f}C "
                        f"mq2={latest['mq2']} flame={latest['flame_raw']} "
                        f"→ alarm={1 if alarm else 0} decision={decision} "
                        f"risk={risk:.2f}"
                    )

                    try:
                        entry = post_to_thingspeak(
                            latest, flameDetected, risk, alarm, decision
                        )
                        print(f"[POST OK] entry={entry}\n")
                    except Exception as e:
                        print(f"[POST FAIL] {e}\n")

                try:
                    ser.reset_input_buffer()
                except Exception:
                    pass

                next_post = now + POST_INTERVAL_SEC
                last_countdown = -1

if __name__ == "__main__":
    main()

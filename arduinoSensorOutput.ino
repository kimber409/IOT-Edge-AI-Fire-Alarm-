
#include <DHT.h>
#include <SoftwareSerial.h>


SoftwareSerial XBee(2, 3); // RX, TX 

// ---------- MQ-2 ----------
const int MQ2_PIN = A0;

// ---------- Traffic Light ----------
const int RED_PIN   = 8;
const int AMBER_PIN = 9;
const int GREEN_PIN = 10;

// Gas thresholds 
int WARN_THRESHOLD   = 350;
int DANGER_THRESHOLD = 500;
const int HYST = 20;
const int SMOOTH_SAMPLES = 20;

enum GasState { SAFE, WARN, DANGER };
GasState gasState = SAFE;

// ---------- DHT ----------
#define DHTPIN 4
#define DHTTYPE DHT11   
DHT dht(DHTPIN, DHTTYPE);

// ---------- Flame ----------
const int FLAME_DO = 6; // DO pin
bool flameDetected() { return digitalRead(FLAME_DO) == LOW; }

// ---------- Timing ----------
unsigned long lastSendMs = 0;
const unsigned long SEND_EVERY_MS = 1000;

// ---------- Helpers ----------
int readSmoothedMQ2() {
  long sum = 0;
  for (int i = 0; i < SMOOTH_SAMPLES; i++) {
    sum += analogRead(MQ2_PIN);
    delay(5);
  }
  return (int)(sum / SMOOTH_SAMPLES);
}

void setLights(bool r, bool y, bool g) {
  digitalWrite(RED_PIN, r ? HIGH : LOW);
  digitalWrite(AMBER_PIN, y ? HIGH : LOW);
  digitalWrite(GREEN_PIN, g ? HIGH : LOW);
}

const char* gasStateStr(GasState s) {
  switch (s) {
    case SAFE: return "SAFE";
    case WARN: return "WARN";
    default:   return "DANGER";
  }
}

const char* lightStr(bool flame, GasState gs) {
  if (flame || gs == DANGER) return "RED";
  if (gs == WARN) return "AMBER";
  return "GREEN";
}

void setup() {
  pinMode(RED_PIN, OUTPUT);
  pinMode(AMBER_PIN, OUTPUT);
  pinMode(GREEN_PIN, OUTPUT);

  pinMode(FLAME_DO, INPUT);

  Serial.begin(9600);   // USB debug
  XBee.begin(9600);     // XBee link 

  dht.begin();

  Serial.println("Arduino safety node starting (sending over XBee)...");
}

void loop() {
  int mq2 = readSmoothedMQ2();
  bool flame = flameDetected();

  // Gas state machine 
  switch (gasState) {
    case SAFE:
      if (mq2 > WARN_THRESHOLD + HYST) gasState = WARN;
      break;
    case WARN:
      if (mq2 > DANGER_THRESHOLD + HYST) gasState = DANGER;
      else if (mq2 < WARN_THRESHOLD - HYST) gasState = SAFE;
      break;
    case DANGER:
      if (mq2 < DANGER_THRESHOLD - HYST) gasState = WARN;
      break;
  }

  // Traffic light output
  if (flame || gasState == DANGER) setLights(true, false, false);
  else if (gasState == WARN)       setLights(false, true, false);
  else                             setLights(false, false, true);

  // Send packet once per second
  unsigned long now = millis();
  if (now - lastSendMs >= SEND_EVERY_MS) {
    lastSendMs = now;

    float t = dht.readTemperature();
    bool tempValid = !(isnan(t) || t < -40 || t > 80);

    // Packet format
    XBee.print("S,ms=");
    XBee.print(now);

    XBee.print(",tempC=");
    if (tempValid) XBee.print(t, 1);
    else XBee.print("NA");

    XBee.print(",mq2=");
    XBee.print(mq2);

    XBee.print(",gas=");
    XBee.print(gasStateStr(gasState));

    XBee.print(",flame=");
    XBee.print(flame ? 1 : 0);

    XBee.print(",light=");
    XBee.print(lightStr(flame, gasState));

    XBee.print("\r\n"); 

    // Optional USB debug
    Serial.println("Sent packet over XBee");
  }
}
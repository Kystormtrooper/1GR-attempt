#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>

// Keeping BLE includes in case you want them later, but USB recording is the focus.
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

#include <cstring>
#include <math.h>

// ==================== RECORDING CONTROLS ====================
bool recording = false;
bool debugOn = true;
int currentLabel = 0;  // press 0-9 to set

// ==================== FLEX PINS ====================
const int PINKEY_PIN = A3;
const int INDEX_PIN  = A5;
const int MIDDLE_PIN = A4;
const int RING_PIN   = A2;

// ==================== BASELINES (RAW, OPEN HAND) ====================
int pinkeyBaseline  = 0;
int indexBaseline   = 0;
int middleBaseline  = 0;
int ringBaseline    = 0;

// ==================== DIRECTION FLAGS ====================
// If your "bent" values are larger than "open", direction should likely be +1.
// Keep -1 if your wiring/voltage divider makes "bent" go DOWN.
const int pinkeyDir  = -1;
const int indexDir   = -1;
const int middleDir  = -1;
const int ringDir    = -1;

// ==================== FILTERS ====================
const float ALPHA = 0.25f;
float pinkeyF = 0, indexF = 0, middleF = 0, ringF = 0;

// ==================== THRESHOLDS ====================
const int INDEX_THRESHOLD  = 200;
const int MIDDLE_THRESHOLD = 200;
const int RING_THRESHOLD   = 200;
const int PINKEY_THRESHOLD = 200;

// ---- Pitch->elevNumber tuning ----
// With ELEV_POLARITY = 1.0, elevNumber follows pitchLPF directly.
// Flip to -1.0 if your zones feel inverted.
const float ELEV_POLARITY = 1.0f;
const float ELEV_OFFSET   = 0.0f;

// ==================== ACTION COOLDOWN ====================
const unsigned long COOLDOWN_MS = 400;
unsigned long lastActionMs = 0;

// ==================== MPU ====================
Adafruit_MPU6050 mpu;

// ==================== MAGNITUDES / GESTURE PARAMS ====================
float gmagPrev = 0.0f;

const float TWIST_TH = 2.0f;   // LOW zone fist + twist => WATCHING_YOU
const float WATCH_GZ = 3.5f;   // optional backup: fist + strong gz => WATCHING_YOU

const float FLICK_GMAG  = 6.0f;
const float FLICK_DELTA = 2.5f;

static inline bool bent(int v, int th) { return v > th; }

static inline float computePitchDeg(float ax, float ay, float az) {
  // pitch: forward/back tilt (degrees)
  float pitchRad = atan2f(-ax, sqrtf(ay * ay + az * az));
  return pitchRad * 180.0f / M_PI;
}
// ==================== PITCH CAL (one-key sequence) ====================
struct PitchCalSeq {
  bool calibrated = false;
  bool running = false;
  unsigned long startMs = 0;

  // accumulators
  float sumHigh = 0, sumMid = 0, sumLow = 0;
  int nHigh = 0, nMid = 0, nLow = 0;

  // results
  float highAvg = 0, midAvg = 0, lowAvg = 0;

  // durations
  const unsigned long HOLD_MS = 4000; // 4 seconds
  const unsigned long MOVE_MS = 2000; // 2 seconds
} pseq;

void startPitchCalibrationSeq() {
  pseq.calibrated = false;
  pseq.running = true;
  pseq.startMs = millis();

  pseq.sumHigh = pseq.sumMid = pseq.sumLow = 0;
  pseq.nHigh = pseq.nMid = pseq.nLow = 0;

  Serial.println("# PITCH CAL: starting -> HIGH 4s, move 2s, MID 4s, move 2s, LOW 4s");
}

// returns true when calibration is finished (or already calibrated)
bool runPitchCalibrationSeq(float pitchValue /* use elevNumber (pitchLPF mapped) */) {
  if (pseq.calibrated) return true;
  if (!pseq.running) return false;

  unsigned long t = millis() - pseq.startMs;

  // Timeline:
  // 0..4s HIGH
  // 4..6s MOVE
  // 6..10s MID
  // 10..12s MOVE
  // 12..16s LOW
  // >16s DONE

  if (t < pseq.HOLD_MS) {
    pseq.sumHigh += pitchValue; pseq.nHigh++;
    if (!recording) Serial.println("# PITCH_CAL,HIGH");
  }
  else if (t < pseq.HOLD_MS + pseq.MOVE_MS) {
    if (!recording) Serial.println("# PITCH_CAL,MOVE->MID");
  }
  else if (t < pseq.HOLD_MS + pseq.MOVE_MS + pseq.HOLD_MS) {
    pseq.sumMid += pitchValue; pseq.nMid++;
    if (!recording) Serial.println("# PITCH_CAL,MID");
  }
  else if (t < pseq.HOLD_MS + pseq.MOVE_MS + pseq.HOLD_MS + pseq.MOVE_MS) {
    if (!recording) Serial.println("# PITCH_CAL,MOVE->LOW");
  }
  else if (t < pseq.HOLD_MS + pseq.MOVE_MS + pseq.HOLD_MS + pseq.MOVE_MS + pseq.HOLD_MS) {
    pseq.sumLow += pitchValue; pseq.nLow++;
    if (!recording) Serial.println("# PITCH_CAL,LOW");
  }
  else {
    // compute averages
    pseq.highAvg = pseq.sumHigh / (pseq.nHigh > 0 ? pseq.nHigh : 1);
    pseq.midAvg  = pseq.sumMid  / (pseq.nMid  > 0 ? pseq.nMid  : 1);
    pseq.lowAvg  = pseq.sumLow  / (pseq.nLow  > 0 ? pseq.nLow  : 1);

    pseq.calibrated = true;
    pseq.running = false;

    if (!recording) {
      Serial.print("# PITCH CAL DONE highAvg="); Serial.print(pseq.highAvg, 2);
      Serial.print(" midAvg=");                  Serial.print(pseq.midAvg, 2);
      Serial.print(" lowAvg=");                  Serial.println(pseq.lowAvg, 2);
    }
  }

  return pseq.calibrated;
}

// Elevation zones
enum ElevZone { Z_LOW = 0, Z_MID = 1, Z_HIGH = 2 };

// ==================== OPTIONAL BLE (not used for USB recording) ====================
static BLEUUID SERVICE_UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E");
static BLEUUID CHAR_TX_UUID ("6E400003-B5A3-F393-E0A9-E50E24DCCA9E");
BLECharacteristic* txChar = nullptr;
bool deviceConnected = false;

static unsigned long lastSentMs = 0;
static int lastSentGesture = -1;
void sendGestureCode(int gid) {
  char msg[8];
  snprintf(msg, sizeof(msg), "G%02d\n", gid);  // e.g., G07\n

  if (deviceConnected && txChar) {
    txChar->setValue((uint8_t*)msg, strlen(msg));
    txChar->notify();
  }
}

class ServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer* pServer) override {
    deviceConnected = true;
    Serial.println("# ✅ BLE connected");
  }
  void onDisconnect(BLEServer* pServer) override {
    deviceConnected = false;
    Serial.println("# ⚠️ BLE disconnected, advertising again");
    BLEDevice::startAdvertising();
  }
};

void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println("# Controls:");
  Serial.println("#   b = set flex baselines (open hand)");
  Serial.println("#   k = start pitch calibration (HIGH 4s, move 2s, MID 4s, move 2s, LOW 4s)");
  Serial.println("#   r = toggle recording");
  Serial.println("#   0-9 = set label");
  Serial.println("# NOTE: CSV rows only print when REC=ON");

  // Updated CSV header with pitch + elevNumber + zone
  Serial.println("ts,label,pinkeyF,indexF,middleF,ringF,pinkeyBent,indexBent,middleBent,ringBent,ax,ay,az,pitchDeg,pitchLPF,gx,gy,gz,gmag,amag,gmagDelta,elevNumber,zone,twist,event,gid");

  Wire.begin();

  if (!mpu.begin()) {
    Serial.println("# MPU6050 not found. Check wiring (SDA/SCL/VCC/GND).");
    while (1) delay(10);
  }

  mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);

  // Prime EMA filters
  int p0 = analogRead(PINKEY_PIN);
  int i0 = analogRead(INDEX_PIN);
  int m0 = analogRead(MIDDLE_PIN);
  int r0 = analogRead(RING_PIN);

  pinkeyF = pinkeyDir * (p0 - pinkeyBaseline);
  indexF  = indexDir  * (i0 - indexBaseline);
  middleF = middleDir * (m0 - middleBaseline);
  ringF   = ringDir   * (r0 - ringBaseline);

  // BLE init (optional; safe to keep enabled)
  BLEDevice::init("GLOVE-ESP32");
  BLEServer* server = BLEDevice::createServer();
  server->setCallbacks(new ServerCallbacks());
  BLEService* service = server->createService(SERVICE_UUID);

  txChar = service->createCharacteristic(
    CHAR_TX_UUID,
    BLECharacteristic::PROPERTY_NOTIFY | BLECharacteristic::PROPERTY_READ
  );
  txChar->addDescriptor(new BLE2902());
  service->start();

  BLEAdvertising* adv = BLEDevice::getAdvertising();
  adv->addServiceUUID(SERVICE_UUID);
  adv->setScanResponse(true);
  adv->setMinPreferred(0x06);
  adv->setMinPreferred(0x12);

  BLEDevice::startAdvertising();
  Serial.println("# ✅ BLE advertising started: GLOVE-ESP32");
}

void loop() {
  static unsigned long t0 = 0;
  if (millis() - t0 > 2000) {
    t0 = millis();
    Serial.println("G12");
  }
  unsigned long ts = millis();

  // ---------------- Serial commands ----------------
  if (Serial.available()) {
    char c = Serial.read();

    if (c == 'b' || c == 'B') {
      pinkeyBaseline  = analogRead(PINKEY_PIN);
      indexBaseline   = analogRead(INDEX_PIN);
      middleBaseline  = analogRead(MIDDLE_PIN);
      ringBaseline    = analogRead(RING_PIN);

      Serial.print("# BASELINES set p,i,m,r = ");
      Serial.print(pinkeyBaseline); Serial.print(",");
      Serial.print(indexBaseline);  Serial.print(",");
      Serial.print(middleBaseline); Serial.print(",");
      Serial.println(ringBaseline);
    }
    else if (c == 'k' || c == 'K') {
      startPitchCalibrationSeq();
    }
    else if (c == 'r' || c == 'R') {
      recording = !recording;
      Serial.print("# REC=");
      Serial.println(recording ? "ON" : "OFF");
    }
    else if (c >= '0' && c <= '9') {
      currentLabel = c - '0';
      Serial.print("# LABEL=");
      Serial.println(currentLabel);
    }
    else if (c == 'd' || c == 'D') {
      debugOn = !debugOn;
      Serial.print("# DEBUG=");
      Serial.println(debugOn ? "ON" : "OFF");
    }
  }

  // ---------------- Read FLEX raw ----------------
  int pinkeyRaw = analogRead(PINKEY_PIN);
  int indexRaw  = analogRead(INDEX_PIN);
  int middleRaw = analogRead(MIDDLE_PIN);
  int ringRaw   = analogRead(RING_PIN);

  int pinkey = pinkeyDir * (pinkeyRaw - pinkeyBaseline);
  int index  = indexDir  * (indexRaw  - indexBaseline);
  int middle = middleDir * (middleRaw - middleBaseline);
  int ring   = ringDir   * (ringRaw   - ringBaseline);

  pinkeyF = ALPHA * pinkey + (1.0f - ALPHA) * pinkeyF;
  indexF  = ALPHA * index  + (1.0f - ALPHA) * indexF;
  middleF = ALPHA * middle + (1.0f - ALPHA) * middleF;
  ringF   = ALPHA * ring   + (1.0f - ALPHA) * ringF;

  bool pinkeyBent = bent((int)pinkeyF, PINKEY_THRESHOLD);
  bool indexBent  = bent((int)indexF,  INDEX_THRESHOLD);
  bool middleBent = bent((int)middleF, MIDDLE_THRESHOLD);
  bool ringBent   = bent((int)ringF,   RING_THRESHOLD);

  // ---------------- Read MPU ----------------
  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);

  float ax = a.acceleration.x;
  float ay = a.acceleration.y;
  float az = a.acceleration.z;

  // Raw pitch (deg)
  float pitchDeg = computePitchDeg(ax, ay, az);

  // Smooth pitch
  static float pitchLPF = 0.0f;
  const float PITCH_ALPHA = 0.15f;     // 0.10-0.25
  pitchLPF = (1.0f - PITCH_ALPHA) * pitchLPF + PITCH_ALPHA * pitchDeg;

  // Visible + calibrated axis you care about
  float elevNumber = ELEV_POLARITY * pitchLPF + ELEV_OFFSET;

  // Debug pitch (only when not recording so CSV stays clean)
  if (!recording && debugOn) {
    Serial.print("# pitchDeg="); Serial.print(pitchDeg, 2);
    Serial.print(" pitchLPF=");  Serial.print(pitchLPF, 2);
    Serial.print(" elevNumber=");Serial.println(elevNumber, 2);
  }

  // ---------------- Pitch calibration sequence ----------------
  // If not calibrated yet:
  // - if running, keep collecting and don't run gesture logic yet
  // - if not running, remind to press 'k'
  if (!pseq.calibrated) {
    if (pseq.running) {
      runPitchCalibrationSeq(elevNumber);
      delay(20);
      return;
    } else {
      if (!recording) Serial.println("# Pitch not calibrated. Press 'k' to calibrate.");
      delay(50);
      return;
    }
  }

  // ---------------- Zone thresholds from calibrated HIGH/MID/LOW ----------------
  float THRESH_LOW_MID  = 0.5f * (pseq.lowAvg + pseq.midAvg);
  float THRESH_MID_HIGH = 0.5f * (pseq.midAvg + pseq.highAvg);

  // Ensure ordering even if averages come in flipped
  if (THRESH_LOW_MID > THRESH_MID_HIGH) {
    float tmp = THRESH_LOW_MID;
    THRESH_LOW_MID = THRESH_MID_HIGH;
    THRESH_MID_HIGH = tmp;
  }

  // Stable zone with hysteresis
  static ElevZone zone = Z_MID;
  const float HYS = 3.0f; // tune 2-5 if needed

  if (zone == Z_LOW) {
    if (elevNumber > THRESH_LOW_MID + HYS) zone = Z_MID;
  } else if (zone == Z_MID) {
    if (elevNumber < THRESH_LOW_MID - HYS) zone = Z_LOW;
    else if (elevNumber > THRESH_MID_HIGH + HYS) zone = Z_HIGH;
  } else { // Z_HIGH
    if (elevNumber < THRESH_MID_HIGH - HYS) zone = Z_MID;
  }

  // ---------------- Derived values ----------------
  bool fistClosed = pinkeyBent && indexBent && middleBent && ringBent;
  bool handOpen   = !pinkeyBent && !indexBent && !middleBent && !ringBent;

  float gx = g.gyro.x, gy = g.gyro.y, gz = g.gyro.z;

  float gmag = sqrtf(gx*gx + gy*gy + gz*gz);
  float amag = sqrtf(ax*ax + ay*ay + az*az);
  float gmagDelta = gmag - gmagPrev;
  gmagPrev = gmag;

  float twist = fmaxf(fabsf(gx), fmaxf(fabsf(gy), fabsf(gz)));

  // ---------------- Gesture logic (NO PINCH) ----------------
  // ---------------- Gesture logic: fire ONCE per closed->open->closed cycle ----------------
  // ---------------- One-shot FIST (must open to re-arm) ----------------
  unsigned long now = millis();

  // Decide pose conditions
  bool fistPoseHigh = fistClosed && (zone == Z_HIGH);
  bool watchPoseLow = fistClosed && (zone == Z_LOW) && (twist > TWIST_TH);
  bool flickPose    = handOpen && (gmag > FLICK_GMAG) && (fabsf(gmagDelta) > FLICK_DELTA);
  bool pointPose    = (!pinkeyBent && indexBent && !middleBent && !ringBent);

  // Re-arm logic: require a few consecutive OPEN frames
  static bool fistArmed = true;
  static int openStreak = 0;
  const int OPEN_REARM_FRAMES = 4;   // ~4*20ms = ~80ms (tune 3-8)

  if (handOpen) openStreak++;
  else openStreak = 0;

  if (openStreak >= OPEN_REARM_FRAMES) {
    fistArmed = true;   // you opened long enough, next fist may fire again
  }

  // Fire events
  int gestureId = 0;
  const char* event = "NONE";

  // Priority events (WATCHING_YOU can also be latched if you want)
  if (now - lastActionMs >= COOLDOWN_MS) {

    // WATCHING_YOU fires whenever condition becomes true (optional latch can be added too)
    if (watchPoseLow) {
      gestureId = 21;
      event = "WATCHING_YOU";
      lastActionMs = now;
    }

    // FIST fires once, then disarms until you open
    else if (fistPoseHigh && fistArmed) {
      gestureId = 7;
      event = "FIST";
      fistArmed = false;
      lastActionMs = now;
    }

    // Other one-shot events (these are naturally transient)
    else if (flickPose) {
      gestureId = 12;
      event = "FLICK";
      lastActionMs = now;
    }
    else if (pointPose) {
      gestureId = 3;
      event = "POINT";
      lastActionMs = now;
    }
  }
  // ----- Send event (BLE + USB Serial) -----
  const unsigned long SEND_COOLDOWN_MS = 350;

  if (gestureId != 0) {
    if ((now - lastSentMs) >= SEND_COOLDOWN_MS || gestureId != lastSentGesture) {
      // BLE notify (if connected)
      sendGestureCode(gestureId);

      // USB serial (Python on COM3 can parse this)
      Serial.printf("G%02d\n", gestureId);

      lastSentMs = now;
      lastSentGesture = gestureId;
    }
  }

  // Debug
  // Debug (human-readable, Python can still parse "# EVT=Gxx" if we allow it)
  if (!recording && debugOn) {
    Serial.print("# elevNumber="); Serial.print(elevNumber, 2);
    Serial.print(" TH_LM="); Serial.print(THRESH_LOW_MID, 2);
    Serial.print(" TH_MH="); Serial.print(THRESH_MID_HIGH, 2);
    Serial.print(" zone="); Serial.print((int)zone);

    Serial.print(" fistClosed="); Serial.print(fistClosed);
    Serial.print(" handOpen="); Serial.print(handOpen);
    Serial.print(" openStreak="); Serial.print(openStreak);
    Serial.print(" fistArmed="); Serial.print(fistArmed);

    Serial.print(" EVT=G");
    if (gestureId < 10) Serial.print("0");
    Serial.print(gestureId);
  }

  // ---------------- CSV output (recording only) ----------------
  if (recording) {
    Serial.print(ts); Serial.print(",");
    Serial.print(currentLabel); Serial.print(",");

    Serial.print((int)pinkeyF); Serial.print(",");
    Serial.print((int)indexF);  Serial.print(",");
    Serial.print((int)middleF); Serial.print(",");
    Serial.print((int)ringF);   Serial.print(",");

    Serial.print((int)pinkeyBent); Serial.print(",");
    Serial.print((int)indexBent);  Serial.print(",");
    Serial.print((int)middleBent); Serial.print(",");
    Serial.print((int)ringBent);   Serial.print(",");

    Serial.print(ax); Serial.print(",");
    Serial.print(ay); Serial.print(",");
    Serial.print(az); Serial.print(",");

    Serial.print(pitchDeg, 2); Serial.print(",");
    Serial.print(pitchLPF, 2); Serial.print(",");

    Serial.print(gx); Serial.print(",");
    Serial.print(gy); Serial.print(",");
    Serial.print(gz); Serial.print(",");

    Serial.print(gmag);      Serial.print(",");
    Serial.print(amag);      Serial.print(",");
    Serial.print(gmagDelta); Serial.print(",");

    Serial.print(elevNumber, 2); Serial.print(",");
    Serial.print((int)zone);     Serial.print(",");
    Serial.print(twist, 2);      Serial.print(",");

    Serial.print(twist, 2); Serial.print(",");
    Serial.print(event); Serial.print(",");
    Serial.print("G");
    if (gestureId < 10) Serial.print("0");
    Serial.println(gestureId);
  }

  delay(20);
}
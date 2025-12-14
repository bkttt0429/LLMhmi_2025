#include <ESP8266WiFi.h>
#include <WiFiUdp.h>
#include <Servo.h>
#include <DHT.h>

// --- Configuration ---
const char* ssid = "Bk";
const char* password = "........."; // Please update credentials in IDE
const int udpPort = 4211;
const IPAddress broadcastIP(255, 255, 255, 255);

// --- Pin Definitions (D1 - D8) ---
#define PIN_SERVO_BASE     5   // D1
#define PIN_SERVO_SHOULDER 4   // D2
#define PIN_SERVO_ELBOW    0   // D3
#define PIN_SERVO_GRIPPER  2   // D4

#define PIN_US_ECHO        14  // D5
#define PIN_VIB            12  // D6
#define PIN_DHT            13  // D7
#define PIN_US_TRIG        15  // D8

// --- Ramping Configuration ---
// Degrees per loop cycle (20ms)
// 1 deg/20ms = 50 deg/sec (Slow/Smooth)
// 3 deg/20ms = 150 deg/sec (Fast)
#define RAMP_SPEED 2 

// --- Objects ---
Servo servoBase;
Servo servoShoulder;
Servo servoElbow;
Servo servoGripper;
DHT dht(PIN_DHT, DHT11);
WiFiUDP Udp;

// --- State ---
unsigned long lastSensorTime = 0;
unsigned long lastServoTime = 0;
const int SENSOR_INTERVAL = 200; // 5Hz Telemetry
const int SERVO_INTERVAL = 20;   // 50Hz Control Loop

// Target Positions
struct ServoState {
  int current;
  int target;
  Servo* servo;
};

ServoState arm[4]; // 0:Base, 1:Shoulder, 2:Elbow, 3:Gripper

void setup() {
  Serial.begin(115200);
  
  // 1. Init Pins
  pinMode(PIN_US_TRIG, OUTPUT);
  pinMode(PIN_US_ECHO, INPUT);
  pinMode(PIN_VIB, INPUT);
  digitalWrite(PIN_US_TRIG, LOW);

  // 2. Init Servos & State
  arm[0].servo = &servoBase;     arm[0].servo->attach(PIN_SERVO_BASE);
  arm[1].servo = &servoShoulder; arm[1].servo->attach(PIN_SERVO_SHOULDER);
  arm[2].servo = &servoElbow;    arm[2].servo->attach(PIN_SERVO_ELBOW);
  arm[3].servo = &servoGripper;  arm[3].servo->attach(PIN_SERVO_GRIPPER);

  // Set Initial Pose (Home)
  int initialPose[4] = {90, 90, 90, 90};
  for(int i=0; i<4; i++) {
    arm[i].target = initialPose[i];
    arm[i].current = initialPose[i];
    arm[i].servo->write(arm[i].current);
  }

  // 3. Init DHT
  dht.begin();

  // 4. WiFi
  WiFi.mode(WIFI_STA);
  WiFi.setSleepMode(WIFI_NONE_SLEEP); // [CRITICAL] Fix Servo Jitter
  WiFi.setAutoReconnect(true);
  WiFi.begin(ssid, password);
  
  Serial.print("Connecting");
  int retry = 0;
  while (WiFi.status() != WL_CONNECTED && retry < 20) {
    delay(500);
    Serial.print(".");
    retry++;
  }
  if (WiFi.status() == WL_CONNECTED) {
      Serial.println("\nConnected!");
      Serial.print("IP: "); Serial.println(WiFi.localIP());
  } else {
      Serial.println("\nWiFi Failed (Will retry in loop)");
  }

  // 5. UDP
  Udp.begin(udpPort);
}

// Simple JSON Parser
int extractValue(String json, String key) {
  int start = json.indexOf("\"" + key + "\":");
  if (start == -1) return -1;
  start = json.indexOf(":", start) + 1;
  int end = json.indexOf(",", start);
  if (end == -1) end = json.indexOf("}", start);
  if (end == -1) return -1;
  return json.substring(start, end).toInt();
}

void updateServos() {
  bool anyMoving = false;
  for(int i=0; i<4; i++) {
    if (arm[i].current != arm[i].target) {
      anyMoving = true;
      int diff = arm[i].target - arm[i].current;
      int step = RAMP_SPEED;
      
      if (abs(diff) < step) {
        arm[i].current = arm[i].target;
        Serial.printf("[SERVO-%d] Reached Target: %d\n", i, arm[i].current); // LOG STOP
      } else {
        if (diff > 0) arm[i].current += step;
        else arm[i].current -= step;
      }
      arm[i].servo->write(arm[i].current);
      // [DEBUG] Confirm Signal Output
      Serial.printf("[PWM] Ch:%d Val:%d\n", i, arm[i].current);
    }
  }
}

void loop() {
  // --- 1. WiFi Maintain ---
  if (WiFi.status() != WL_CONNECTED) {
     // ESP8266 handles reconnect automatically, but we can blink LED or debug here
  }

  // --- 2. Servo Ramping Loop (50Hz) ---
  if (millis() - lastServoTime >= SERVO_INTERVAL) {
    lastServoTime = millis();
    updateServos();
  }

  // --- 3. UDP Control Receiver ---
  int packetSize = Udp.parsePacket();
  if (packetSize) {
    String packet = Udp.readStringUntil('\0');
    // Expect: {"base":90,"shoulder":45,"elbow":90,"gripper":0}
    Serial.print("[UDP] Rx: "); Serial.println(packet); // LOG PACKET
    
    int b = extractValue(packet, "base");
    int s = extractValue(packet, "shoulder");
    int e = extractValue(packet, "elbow");
    int g = extractValue(packet, "gripper");

    // Helper to Log Target Changes
    auto updateTarget = [&](int idx, int val, String name) {
        if (val >= 0 && arm[idx].target != val) {
            arm[idx].target = constrain(val, 0, 180);
            Serial.printf("[CMD] %s Target: %d -> %d\n", name.c_str(), arm[idx].current, arm[idx].target);
        }
    };

    updateTarget(0, b, "Base");
    updateTarget(1, s, "Shoulder");
    updateTarget(2, e, "Elbow");
    updateTarget(3, g, "Gripper");
  }

  // --- 4. Sensor Telemetry --
  if (millis() - lastSensorTime > SENSOR_INTERVAL) {
    lastSensorTime = millis();

    // A. Ultrasonic
    digitalWrite(PIN_US_TRIG, LOW); delayMicroseconds(2);
    digitalWrite(PIN_US_TRIG, HIGH); delayMicroseconds(10);
    digitalWrite(PIN_US_TRIG, LOW);
    long duration = pulseIn(PIN_US_ECHO, HIGH, 25000); 
    float dist = (duration == 0) ? -1 : (duration * 0.034 / 2);

    // B. DHT
    float h = dht.readHumidity();
    float t = dht.readTemperature();
    if (isnan(h) || isnan(t)) { h = 0; t = 0; }

    int vib = digitalRead(PIN_VIB); 

    // Send JSON: {"device":"esp8266-arm","ip":"...","dist":...}
    // Added 'device' and 'ip' to help PC Client discovery
    String msg = "{";
    msg += "\"device\":\"esp8266-arm\",";
    msg += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
    msg += "\"dist\":" + String(dist, 1) + ",";
    msg += "\"temp\":" + String(t, 1) + ",";
    msg += "\"humid\":" + String(h, 1) + ",";
    msg += "\"vib\":" + String(vib);
    msg += "}";

    // UDP allows broadcast even if not connected (sometimes), but better check
    if (WiFi.status() == WL_CONNECTED) {
      Udp.beginPacket(broadcastIP, udpPort);
      Udp.write(msg.c_str());
      Udp.endPacket();
    }
  }
}

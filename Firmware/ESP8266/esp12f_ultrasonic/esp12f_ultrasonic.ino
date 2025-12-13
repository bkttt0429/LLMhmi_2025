#include <ESP8266WiFi.h>
#include <WiFiUdp.h>
#include <Servo.h>
#include "DHT.h"

// --- Configuration ---
const char* ssid = "Bk";
const char* password = ".........";
const int udpPort = 4211;
const IPAddress broadcastIP(255, 255, 255, 255);

// --- Pin Definitions (D1 - D8) ---
// Servos
#define PIN_SERVO_BASE     5   // D1
#define PIN_SERVO_SHOULDER 4   // D2
#define PIN_SERVO_ELBOW    0   // D3
#define PIN_SERVO_GRIPPER  2   // D4

// Sensors
#define PIN_US_ECHO        14  // D5
#define PIN_VIB            12  // D6
#define PIN_DHT            13  // D7
#define PIN_US_TRIG        15  // D8 (Boot: Must be LOW)

// --- Objects ---
Servo servoBase;
Servo servoShoulder;
Servo servoElbow;
Servo servoGripper;
DHT dht(PIN_DHT, DHT11); // Assume DHT11, change to DHT22 if needed
WiFiUDP Udp;

// --- State ---
unsigned long lastSensorTime = 0;
const int SENSOR_INTERVAL = 200; // 5Hz Telemetry

void setup() {
  Serial.begin(115200);
  
  // 1. Init Pins
  pinMode(PIN_US_TRIG, OUTPUT);
  pinMode(PIN_US_ECHO, INPUT);
  pinMode(PIN_VIB, INPUT);
  digitalWrite(PIN_US_TRIG, LOW); // Keep D8 Low

  // 2. Init Servos
  servoBase.attach(PIN_SERVO_BASE);
  servoShoulder.attach(PIN_SERVO_SHOULDER);
  servoElbow.attach(PIN_SERVO_ELBOW);
  servoGripper.attach(PIN_SERVO_GRIPPER);

  // Initial Pose
  servoBase.write(90);
  servoShoulder.write(90);
  servoElbow.write(90);
  servoGripper.write(90); 

  // 3. Init DHT
  dht.begin();

  // 4. WiFi
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  Serial.print("Connecting");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nCombined Connected!");
  Serial.print("IP: "); Serial.println(WiFi.localIP());

  // 5. UDP
  Udp.begin(udpPort);
}

// Simple JSON Parser helper
int extractValue(String json, String key) {
  int start = json.indexOf("\"" + key + "\":");
  if (start == -1) return -1; // Not found
  start = json.indexOf(":", start) + 1;
  int end = json.indexOf(",", start);
  if (end == -1) end = json.indexOf("}", start);
  if (end == -1) return -1;
  return json.substring(start, end).toInt();
}

void loop() {
  // --- 1. UDP Control Receiver (Fast) ---
  int packetSize = Udp.parsePacket();
  if (packetSize) {
    String packet = Udp.readStringUntil('\0');
    // Expect: {"base":90,"shoulder":45,"elbow":90,"gripper":0}
    
    int b = extractValue(packet, "base");
    int s = extractValue(packet, "shoulder");
    int e = extractValue(packet, "elbow");
    int g = extractValue(packet, "gripper");

    if (b >= 0) servoBase.write(b);
    if (s >= 0) servoShoulder.write(s);
    if (e >= 0) servoElbow.write(e);
    if (g >= 0) servoGripper.write(g);
  }

  // --- 2. Sensor Telemetry (Timed) ---
  if (millis() - lastSensorTime > SENSOR_INTERVAL) {
    lastSensorTime = millis();

    // A. Ultrasonic
    digitalWrite(PIN_US_TRIG, LOW); delayMicroseconds(2);
    digitalWrite(PIN_US_TRIG, HIGH); delayMicroseconds(10);
    digitalWrite(PIN_US_TRIG, LOW);
    long duration = pulseIn(PIN_US_ECHO, HIGH, 25000); // 25ms timeout
    float dist = (duration == 0) ? -1 : (duration * 0.034 / 2);

    // B. DHT
    float h = dht.readHumidity();
    float t = dht.readTemperature();
    if (isnan(h) || isnan(t)) { h = 0; t = 0; }

    // C. Vibration (Instantaneous)
    // For better vibration detection, we should poll frequently, but for now just sample.
    int vib = digitalRead(PIN_VIB); 

    // Send JSON: {"dist":25.0,"temp":26.0,"humid":60.0,"vib":1}
    String msg = "{";
    msg += "\"dist\":" + String(dist, 1) + ",";
    msg += "\"temp\":" + String(t, 1) + ",";
    msg += "\"humid\":" + String(h, 1) + ",";
    msg += "\"vib\":" + String(vib);
    msg += "}";

    Udp.beginPacket(broadcastIP, udpPort);
    Udp.write(msg.c_str());
    Udp.endPacket();
  }
}

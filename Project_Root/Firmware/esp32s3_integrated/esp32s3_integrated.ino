/**
 * ESP32-S3 Integrated Firmware (Camera + Car Control)
 * Hardware: ESP32-S3 (e.g., N16R8)
 * Mode: AP Mode (Single Chip Solution)
 *
 * Pinout:
 *   [Camera]     (Standard ESP32-S3-CAM)
 *   [Ultrasonic] GPIO 21
 *   [Servo Left] GPIO 14
 *   [Servo Right] GPIO 2 (or 47 depending on board)
 *   [LED]        GPIO 48
 *
 * Network:
 *   SSID: ESP32_Car
 *   Pass: password
 *   IP:   192.168.4.1
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <WiFiUdp.h>
#include <WebServer.h>

// ============= WiFi AP Settings =============
const char* ssid_ap     = "ESP32_Car";
const char* password_ap = "password";

// ============= IP Settings =============
IPAddress local_ip(192, 168, 4, 1);
IPAddress gateway(192, 168, 4, 1);
IPAddress subnet(255, 255, 255, 0);

// ============= Hardware Pins (Camera) =============
#define PWDN_GPIO_NUM     -1
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM     15
#define SIOD_GPIO_NUM     4
#define SIOC_GPIO_NUM     5
#define Y9_GPIO_NUM       16
#define Y8_GPIO_NUM       17
#define Y7_GPIO_NUM       18
#define Y6_GPIO_NUM       12
#define Y5_GPIO_NUM       10
#define Y4_GPIO_NUM       8
#define Y3_GPIO_NUM       9
#define Y2_GPIO_NUM       11
#define VSYNC_GPIO_NUM    6
#define HREF_GPIO_NUM     7
#define PCLK_GPIO_NUM     13
#define LED_PIN           48

// ============= Hardware Pins (Peripherals) =============
#define US_SIG_PIN        21
#define SERVO_LEFT_PIN    14
#define SERVO_RIGHT_PIN   2   // Change to 47 if needed

// ============= PWM Settings (No Library) =============
// Use high channels to avoid conflict with Camera (usually uses Ch 0/1)
#define PWM_FREQ          50
#define PWM_RES           16   // 16-bit resolution (0-65535)
#define LEFT_CHANNEL      2
#define RIGHT_CHANNEL     3

// ============= Globals =============
WebServer server(80); // Combined server on Port 80
WiFiClient streamClient;

bool streamActive = false;
unsigned long lastStreamFrame = 0;
const uint16_t TARGET_FPS_INTERVAL_MS = 40;  // ~25 FPS

const int STOP_VAL = 1500;
// Speed Constants
const int SPEED_FWD_L = 1700;
const int SPEED_BCK_L = 1300;
const int SPEED_FWD_R = 1300;
const int SPEED_BCK_R = 1700;

// Arc Turns
const int ARC_INNER_FWD_L = 1550;
const int ARC_OUTER_FWD_L = 1700;
const int ARC_INNER_FWD_R = 1450;
const int ARC_OUTER_FWD_R = 1300;

const int ARC_INNER_BCK_L = 1450;
const int ARC_OUTER_BCK_L = 1300;
const int ARC_INNER_BCK_R = 1550;
const int ARC_OUTER_BCK_R = 1700;

// Smooth Control
int currentLeftSpeed = STOP_VAL;
int currentRightSpeed = STOP_VAL;
int targetLeftSpeed = STOP_VAL;
int targetRightSpeed = STOP_VAL;
const int SMOOTH_STEP = 20;

unsigned long lastCmdTime = 0;
const unsigned long CMD_TIMEOUT_MS = 2000;

// ============= Function Declarations =============
bool init_camera();      // Fixed return type
void init_ultrasonic();
float get_distance();
void init_servos();
void setSpeed(int l, int r);
void stopCar();
void writeServo(int channel, int us);

// ============= Ultrasonic =============
void init_ultrasonic() {
  pinMode(US_SIG_PIN, INPUT_PULLDOWN);
  Serial.println("[OK] Ultrasonic Init");
}

float get_distance() {
  pinMode(US_SIG_PIN, OUTPUT);
  digitalWrite(US_SIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(US_SIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(US_SIG_PIN, LOW);
  pinMode(US_SIG_PIN, INPUT_PULLUP);
  unsigned long duration = pulseIn(US_SIG_PIN, HIGH, 30000); // 30ms timeout
  if (duration == 0) return -1.0;
  return duration * 0.034 / 2.0;
}

// ============= Servo Logic (Native LEDC) =============
void writeServo(int channel, int us) {
  // 50Hz = 20ms = 20000us
  // Resolution 16-bit = 65536 steps
  // Duty = (us / 20000) * 65536
  uint32_t duty = (us * 65536) / 20000;
  ledcWrite(channel, duty);
}

void init_servos() {
    // Setup PWM channels
    // Note: ledcSetup is for ESP32 Arduino Core v2.x.
    // If using v3.x, APIs changed (ledcAttach).
    // We try to support v2.x as it's most common for Camera examples.

    #if ESP_ARDUINO_VERSION_MAJOR >= 3
      ledcAttach(SERVO_LEFT_PIN, PWM_FREQ, PWM_RES);
      ledcAttach(SERVO_RIGHT_PIN, PWM_FREQ, PWM_RES);
    #else
      ledcSetup(LEFT_CHANNEL, PWM_FREQ, PWM_RES);
      ledcSetup(RIGHT_CHANNEL, PWM_FREQ, PWM_RES);
      ledcAttachPin(SERVO_LEFT_PIN, LEFT_CHANNEL);
      ledcAttachPin(SERVO_RIGHT_PIN, RIGHT_CHANNEL);
    #endif

    stopCar();
    Serial.println("[OK] Servos Init (Native PWM)");
}

void setSpeed(int leftTarget, int rightTarget) {
  targetLeftSpeed = leftTarget;
  targetRightSpeed = rightTarget;
  lastCmdTime = millis();
}

void stopCar() {
  targetLeftSpeed = STOP_VAL;
  targetRightSpeed = STOP_VAL;
}

void smoothUpdate() {
  if (currentLeftSpeed < targetLeftSpeed) currentLeftSpeed = min(currentLeftSpeed + SMOOTH_STEP, targetLeftSpeed);
  else if (currentLeftSpeed > targetLeftSpeed) currentLeftSpeed = max(currentLeftSpeed - SMOOTH_STEP, targetLeftSpeed);

  if (currentRightSpeed < targetRightSpeed) currentRightSpeed = min(currentRightSpeed + SMOOTH_STEP, targetRightSpeed);
  else if (currentRightSpeed > targetRightSpeed) currentRightSpeed = max(currentRightSpeed - SMOOTH_STEP, targetRightSpeed);

  // Update Motor Hardware
  #if ESP_ARDUINO_VERSION_MAJOR >= 3
    // For v3, ledcWrite takes pin, not channel? No, usually ledcWrite(pin, duty)
    // Actually v3 API: ledcWrite(pin, duty).
    // We need to check if user is on v3. For safety, we abstracted `writeServo` but implementation differs.
    // Let's implement writeServo logic inline or separate.

    // Actually, ledcWrite in v3 takes (pin, value). In v2 it takes (channel, value).
    // This makes helper tricky. Let's do this:

    uint32_t dutyL = (currentLeftSpeed * 65536) / 20000;
    uint32_t dutyR = (currentRightSpeed * 65536) / 20000;

    ledcWrite(SERVO_LEFT_PIN, dutyL);
    ledcWrite(SERVO_RIGHT_PIN, dutyR);

  #else
    writeServo(LEFT_CHANNEL, currentLeftSpeed);
    writeServo(RIGHT_CHANNEL, currentRightSpeed);
  #endif
}

void processCommand(String cmd) {
  if (cmd.length() == 0) return;
  Serial.println("CMD: " + cmd);

  // New format: v{left}:{right}
  if (cmd.startsWith("v") || cmd.startsWith("V")) {
    int sep = cmd.indexOf(':');
    if (sep > 1) {
      int l = cmd.substring(1, sep).toInt();
      int r = cmd.substring(sep + 1).toInt();
      l = constrain(l, 1000, 2000);
      r = constrain(r, 1000, 2000);
      setSpeed(l, r);
      return;
    }
  }

  char c = cmd.charAt(0);
  switch (c) {
    case 'F': setSpeed(SPEED_FWD_L, SPEED_FWD_R); break;
    case 'B': setSpeed(SPEED_BCK_L, SPEED_BCK_R); break;
    case 'L': setSpeed(SPEED_BCK_L, SPEED_FWD_R); break;
    case 'R': setSpeed(SPEED_FWD_L, SPEED_BCK_R); break;
    case 'Q': setSpeed(ARC_INNER_FWD_L, ARC_OUTER_FWD_R); break;
    case 'E': setSpeed(ARC_OUTER_FWD_L, ARC_INNER_FWD_R); break;
    case 'Z': setSpeed(ARC_INNER_BCK_L, ARC_OUTER_BCK_R); break;
    case 'C': setSpeed(ARC_OUTER_BCK_L, ARC_INNER_BCK_R); break;
    case 'S': stopCar(); break;
    default: stopCar(); break;
  }
}

// ============= Camera Logic =============
bool init_camera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  if (psramFound()) {
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 12;
    config.fb_count = 2;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.grab_mode = CAMERA_GRAB_LATEST;
  } else {
    config.frame_size = FRAMESIZE_QVGA;
    config.jpeg_quality = 15;
    config.fb_count = 1;
    config.fb_location = CAMERA_FB_IN_DRAM;
  }

  if (esp_camera_init(&config) != ESP_OK) return false;

  sensor_t *s = esp_camera_sensor_get();
  if (s) {
    s->set_vflip(s, 0); // Adjust as needed
    s->set_hmirror(s, 0);
  }
  return true;
}

// ============= HTTP Handlers =============
void handle_stream() {
  if (streamActive && streamClient) {
    streamClient.stop();
    streamActive = false;
  }

  streamClient = server.client();
  if (!streamClient || !streamClient.connected()) return;

  streamClient.setNoDelay(true);
  streamClient.println("HTTP/1.1 200 OK");
  streamClient.println("Content-Type: multipart/x-mixed-replace; boundary=frame");
  streamClient.println("Access-Control-Allow-Origin: *");
  streamClient.println("Connection: close");
  streamClient.println();

  streamActive = true;
  lastStreamFrame = millis();
}

void handle_cmd() {
  if (server.hasArg("act")) {
    processCommand(server.arg("act"));
    server.send(200, "text/plain", "OK");
  } else {
    server.send(400, "text/plain", "Bad Request");
  }
}

void handle_dist() {
  float d = get_distance();
  server.send(200, "text/plain", String(d));
}

void handle_light() {
  if (server.hasArg("on")) {
    bool state = server.arg("on").toInt();
    digitalWrite(LED_PIN, state ? HIGH : LOW);
    server.send(200, "text/plain", state ? "ON" : "OFF");
  }
}

void handle_root() {
  server.send(200, "text/html", "<h1>ESP32-S3 Integrated (AP Mode)</h1><p>Stream: /stream</p><p>CMD: /cmd?act=F</p>");
}

// ============= Setup =============
void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);

  init_ultrasonic();
  init_servos();

  if (!init_camera()) {
    Serial.println("Camera Init Failed");
    while(1) delay(100);
  }

  WiFi.mode(WIFI_AP);
  WiFi.softAPConfig(local_ip, gateway, subnet);
  WiFi.softAP(ssid_ap, password_ap);

  Serial.print("AP IP: "); Serial.println(WiFi.softAPIP());

  server.on("/", handle_root);
  server.on("/stream", handle_stream);
  server.on("/cmd", handle_cmd);
  server.on("/dist", handle_dist);
  server.on("/light", handle_light);
  server.begin();

  // Blink ready
  for(int i=0; i<3; i++) { digitalWrite(LED_PIN, HIGH); delay(100); digitalWrite(LED_PIN, LOW); delay(100); }
}

// ============= Loop =============
void loop() {
  server.handleClient();
  smoothUpdate(); // Update servos

  // Auto-stop safety
  if (millis() - lastCmdTime > CMD_TIMEOUT_MS && (targetLeftSpeed != STOP_VAL || targetRightSpeed != STOP_VAL)) {
    stopCar();
  }

  // Stream logic
  if (streamActive) {
    if (!streamClient || !streamClient.connected()) {
      streamActive = false;
      if (streamClient) streamClient.stop();
      return;
    }

    if (millis() - lastStreamFrame >= TARGET_FPS_INTERVAL_MS) {
      lastStreamFrame = millis();
      camera_fb_t *fb = esp_camera_fb_get();
      if (!fb) return;

      streamClient.print("--frame\r\n");
      streamClient.printf("Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n", fb->len);
      streamClient.write(fb->buf, fb->len);
      streamClient.print("\r\n");

      esp_camera_fb_return(fb);
    }
  }

  delay(1); // Yield
}

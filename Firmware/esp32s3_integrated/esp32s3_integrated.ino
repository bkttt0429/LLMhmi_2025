/**
 * ESP32-S3 Integrated Firmware (Camera + Motor Driver)
 * Hardware: ESP32-S3 (e.g., N16R8)
 * Mode: AP Mode
 *
 * Pinout:
 *   [Camera]     (Standard ESP32-S3-CAM)
 *   [LED]        GPIO 48
 *   [Motor Left] GPIO 21
 *   [Motor Right] GPIO 47
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

// ============= Motor Pins (Servo / PWM) =============
#define MOTOR_LEFT_PIN    21
#define MOTOR_RIGHT_PIN   47

// ============= PWM Settings =============
// NOTE: We use 50Hz for Servo/ESC compatibility to allow Reverse on single pin.
// 1500us = Stop, <1500 Reverse, >1500 Forward.
#define PWM_FREQ          50
#define PWM_RES           16   // 16-bit resolution (0-65535)
#define LEFT_CHANNEL      2
#define RIGHT_CHANNEL     3

// 50Hz Period = 20000us.
// 1000us (5%) = 3276 (approx)
// 1500us (7.5%) = 4915 (approx)
// 2000us (10%) = 6553
const int SERVO_STOP = 1500;
const int SERVO_MIN = 1000;
const int SERVO_MAX = 2000;

// ============= Globals =============
WebServer server(80);
WiFiClient streamClient;
WiFiUDP udp;

const uint16_t UDP_DIST_PORT = 4211;  // Listen from ESP12F
bool streamActive = false;
unsigned long lastStreamFrame = 0;
const uint16_t TARGET_FPS_INTERVAL_MS = 40;  // ~25 FPS
float lastDistance = 0.0;

// ============= Function Declarations =============
bool init_camera();
void init_motors();
void set_motor_pwm(int channel, int us);
void handle_control();

void init_motors() {
    // Setup PWM channels for ESP32 Arduino Core 2.x
    // If using Core 3.x, use ledcAttach(pin, freq, res).
    #if ESP_ARDUINO_VERSION_MAJOR >= 3
      ledcAttach(MOTOR_LEFT_PIN, PWM_FREQ, PWM_RES);
      ledcAttach(MOTOR_RIGHT_PIN, PWM_FREQ, PWM_RES);
    #else
      ledcSetup(LEFT_CHANNEL, PWM_FREQ, PWM_RES);
      ledcSetup(RIGHT_CHANNEL, PWM_FREQ, PWM_RES);
      ledcAttachPin(MOTOR_LEFT_PIN, LEFT_CHANNEL);
      ledcAttachPin(MOTOR_RIGHT_PIN, RIGHT_CHANNEL);
    #endif

    set_motor_pwm(LEFT_CHANNEL, SERVO_STOP);
    set_motor_pwm(RIGHT_CHANNEL, SERVO_STOP);
    Serial.println("[OK] Motors Init (50Hz Servo Mode)");
}

void set_motor_pwm(int channel, int us) {
  // Clamp
  if (us < SERVO_MIN) us = SERVO_MIN;
  if (us > SERVO_MAX) us = SERVO_MAX;

  // Convert us to duty
  // 50Hz = 20000us period
  uint32_t duty = (us * 65536) / 20000;

  #if ESP_ARDUINO_VERSION_MAJOR >= 3
    // channel argument is actually PIN in v3 wrapper helper (simplified)
    // checking if channel is pin...
    if (channel == LEFT_CHANNEL) ledcWrite(MOTOR_LEFT_PIN, duty);
    else if (channel == RIGHT_CHANNEL) ledcWrite(MOTOR_RIGHT_PIN, duty);
  #else
    ledcWrite(channel, duty);
  #endif
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
    s->set_vflip(s, 0);
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

void handle_control() {
  // /control?left=XX&right=YY
  // Input expected: -255 to 255
  if (server.hasArg("left") && server.hasArg("right")) {
    int l_val = server.arg("left").toInt();
    int r_val = server.arg("right").toInt();

    // Map -255..255 to 1000..2000
    // -255 -> 1000
    // 0    -> 1500
    // 255  -> 2000
    int l_us = map(l_val, -255, 255, 1000, 2000);
    int r_us = map(r_val, -255, 255, 1000, 2000);

    set_motor_pwm(LEFT_CHANNEL, l_us);
    set_motor_pwm(RIGHT_CHANNEL, r_us);

    server.send(200, "text/plain", "OK");
  } else {
    server.send(400, "text/plain", "Missing left/right params");
  }
}

void handle_dist() {
  server.send(200, "text/plain", String(lastDistance));
}

void handle_light() {
  if (server.hasArg("on")) {
    bool state = server.arg("on").toInt();
    digitalWrite(LED_PIN, state ? HIGH : LOW);
    server.send(200, "text/plain", state ? "ON" : "OFF");
  }
}

void handle_root() {
  server.send(200, "text/html", "<h1>ESP32-S3 Car (AP Mode)</h1><p>Stream: /stream</p><p>Control: /control?left=X&right=Y</p>");
}

// ============= Setup =============
void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);

  init_motors();

  if (!init_camera()) {
    Serial.println("Camera Init Failed");
    // Don't hang, continue so motors might work
  }

  WiFi.mode(WIFI_AP);
  WiFi.softAPConfig(local_ip, gateway, subnet);
  WiFi.softAP(ssid_ap, password_ap);

  Serial.print("AP IP: "); Serial.println(WiFi.softAPIP());

  udp.begin(UDP_DIST_PORT);
  Serial.printf("UDP Listening on port %d for Distance\n", UDP_DIST_PORT);

  server.on("/", handle_root);
  server.on("/stream", handle_stream);
  server.on("/control", handle_control);
  server.on("/dist", handle_dist);
  server.on("/light", handle_light);
  server.begin();

  // Blink ready
  for(int i=0; i<3; i++) { digitalWrite(LED_PIN, HIGH); delay(100); digitalWrite(LED_PIN, LOW); delay(100); }
}

// ============= Loop =============
void loop() {
  server.handleClient();

  // Listen for Distance updates via UDP from ESP12F
  int packetSize = udp.parsePacket();
  if (packetSize) {
     char buff[32];
     int len = udp.read(buff, 31);
     if (len > 0) {
       buff[len] = 0;
       lastDistance = atof(buff);
     }
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

  delay(1);
}

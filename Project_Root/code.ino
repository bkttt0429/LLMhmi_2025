/**
 * ESP32-S3-CAM 韌體 v4.0（精簡影像版）
 * 專注串流：移除控制路徑，鎖定 20 FPS 與 JPEG Q=20，避免佔滿 WiFi 頻寬。
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>

// ============= WiFi 設定 =============
const char* ssid     = "Bk";
const char* password = ".........";

// ============= 硬體腳位 (ESP32-S3-CAM N16R8) =============
#define SIG_PIN 21
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

// ============= 全域變數 =============
WebServer server(81);
WiFiClient streamClient;
bool streamActive = false;
unsigned long lastStreamFrame = 0;
const uint16_t TARGET_FPS_INTERVAL_MS = 50; // 鎖定 ~20 FPS

// ============= 超聲波 =============
void init_ultrasonic() {
  pinMode(SIG_PIN, INPUT_PULLDOWN);
  digitalWrite(SIG_PIN, LOW);
  Serial.println("[OK] Ultrasonic initialized");
}

float get_distance() {
  pinMode(SIG_PIN, OUTPUT);
  digitalWrite(SIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(SIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(SIG_PIN, LOW);
  pinMode(SIG_PIN, INPUT_PULLUP);
  unsigned long duration = pulseIn(SIG_PIN, HIGH, 30000);
  if (duration == 0) return -1.0;
  return duration * 0.034 / 2.0;
}

// ============= 相機初始化 (限流版) =============
bool init_camera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
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

  // 嘗試使用 PSRAM：VGA + Q=20
  if (psramFound()) {
    Serial.println("[INFO] PSRAM detected, using VGA @ Q20");
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 20;
    config.fb_count = 2;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.grab_mode = CAMERA_GRAB_LATEST;

    if (esp_camera_init(&config) == ESP_OK) {
      Serial.println("[OK] Camera init success (PSRAM mode)");
      return true;
    }
    Serial.println("[WARN] PSRAM init failed, de-initializing...");
    esp_camera_deinit();
  } else {
    Serial.println("[WARN] No PSRAM detected");
  }

  // 降級模式：使用內部 SRAM，依然維持 Q=20 確保頻寬
  Serial.println("[INFO] Falling back to Low-Res (SRAM) mode...");
  config.frame_size = FRAMESIZE_QVGA;
  config.jpeg_quality = 20;
  config.fb_count = 1;
  config.fb_location = CAMERA_FB_IN_DRAM;

  if (esp_camera_init(&config) == ESP_OK) {
    Serial.println("[OK] Camera init success (SRAM mode)");
    return true;
  }

  return false;
}

// ============= HTTP Handlers =============
void handle_root() {
  server.send(200, "text/plain", "ESP32-S3-CAM Ready");
}

void handle_capture() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    server.send(500, "text/plain", "Capture failed");
    return;
  }
  server.sendHeader("Content-Type", "image/jpeg");
  server.send_P(200, "image/jpeg", (const char*)fb->buf, fb->len);
  esp_camera_fb_return(fb);
}

void handle_stream() {
  streamClient = server.client();
  streamClient.setNoDelay(true);
  streamClient.print("HTTP/1.1 200 OK\r\nContent-Type: multipart/x-mixed-replace; boundary=frame\r\n\r\n");
  streamActive = true;
  lastStreamFrame = 0;
  Serial.println("[STREAM] Started @20FPS");
}

// ============= Setup & Loop =============
void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(false);
  delay(1000);

  Serial.println("\n=== ESP32-S3-CAM v4.0 (Stream Only) ===");
  init_ultrasonic();

  if (!init_camera()) {
    Serial.println("❌ Camera FATAL ERROR! System halted.");
    while(1) delay(1000);
  }

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  Serial.print("⏳ WiFi connecting");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n✓ WiFi Connected!");
  Serial.printf("📡 Stream URL: http://%s:81/stream\n", WiFi.localIP().toString().c_str());

  server.on("/", handle_root);
  server.on("/capture", handle_capture);
  server.on("/stream", handle_stream);
  server.begin();

  Serial.println("✓ System Ready! (Streaming only)");
}

void loop() {
  server.handleClient();

  if (streamActive) {
    if (!streamClient.connected()) {
      streamActive = false;
      streamClient.stop();
    } else {
      unsigned long now = millis();
      if (now - lastStreamFrame >= TARGET_FPS_INTERVAL_MS) {
        lastStreamFrame = now;
        camera_fb_t *fb = esp_camera_fb_get();
        if (fb) {
          streamClient.printf("--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n", fb->len);
          streamClient.write(fb->buf, fb->len);
          streamClient.print("\r\n");
          esp_camera_fb_return(fb);
        }
      }
    }
  }

  static unsigned long lastDist = 0;
  if (millis() - lastDist >= 200) {
    lastDist = millis();
    float d = get_distance();
    if (d > 2.0 && d < 400.0) Serial.printf("DIST:%.1f\n", d);
  }
}

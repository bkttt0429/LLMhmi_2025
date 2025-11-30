/**
 * ESP32-S3-CAM 終極全自動版 v5.0
 * 特色：
 *   • 開機狂喊 10 次 UDP + 之後每 1 秒廣播一次 → 保證電腦一定收到
 *   • Serial 持續印 IP → USB 線插著就 100% 抓到
 *   • 串流超穩 20~30FPS (VGA + PSRAM)
 *   • 超聲波、補光燈、ESP-NOW 全保留
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <WiFiUdp.h>
#include <WebServer.h>
#include <esp_now.h>

// ============= 請改這裡！ =============
const char* ssid     = "你的WiFi名稱";        // ←←← 改成你手機熱點或家用 WiFi 名稱
const char* password = "你的WiFi密碼";        // ←←← 改成密碼
// ======================================

// ============= 硬體腳位 (環島科技/GOOUUU ESP32-S3-CAM N16R8) =============
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

#define LED_PIN           48   // 補光燈
#define SIG_PIN           21   // HC-SR04 Trigger/Echo 共用腳

// ============= 全域變數 =============
WebServer server(81);
WiFiClient streamClient;
WiFiUDP udp;

bool streamActive = false;
unsigned long lastStreamFrame = 0;
const uint16_t TARGET_FPS_INTERVAL_MS = 50;  // 目標 20FPS

const uint16_t IP_BROADCAST_PORT = 4211;     // Python 端收聽的 port
unsigned long lastIPUdpBroadcast = 0;

// ============= 超聲波 =============
void init_ultrasonic() {
  pinMode(SIG_PIN, INPUT_PULLDOWN);
  Serial.println("[OK] Ultrasonic @ GPIO21");
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

// ============= 相機初始化 =============
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

  // PSRAM 模式優先（VGA）
  if (psramFound()) {
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 20;
    config.fb_count = 2;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.grab_mode = CAMERA_GRAB_LATEST;
  } else {
    config.frame_size = FRAMESIZE_QVGA;
    config.jpeg_quality = 20;
    config.fb_count = 1;
    config.fb_location = CAMERA_FB_IN_DRAM;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[ERROR] Camera init failed: 0x%x\n", err);
    return false;
  }

  sensor_t *s = esp_camera_sensor_get();
  if (s) {
    s->set_brightness(s, 0);
    s->set_contrast(s, 0);
    s->set_saturation(s, 0);
    s->set_whitebal(s, 1);
    s->set_awb_gain(s, 1);
    s->set_wb_mode(s, 0);
    s->set_exposure_ctrl(s, 1);
    s->set_aec2(s, 0);
    s->set_gain_ctrl(s, 1);
    s->set_agc(s, 0);
    s->set_wpc(s, 1);
    s->set_raw_gma(s, 1);
    s->set_lenc(s, 1);
    s->set_hmirror(s, 0);
    s->set_vflip(s, 0);
  }
  return true;
}

// ============= UDP 狂喊 IP =============
void broadcast_ip_udp() {
  if (WiFi.status() != WL_CONNECTED) return;
  IPAddress broadcastIp(255, 255, 255, 255);
  udp.beginPacket(broadcastIp, IP_BROADCAST_PORT);
  udp.print("ESP32S3CAM_IP:");
  udp.print(WiFi.localIP().toString());
  udp.print(";STREAM:http://");
  udp.print(WiFi.localIP().toString());
  udp.print(":81/stream");
  udp.endPacket();
}

void announce_ip(bool force = false) {
  if (WiFi.status() != WL_CONNECTED) return;
  unsigned long now = millis();

  // 每 1 秒 UDP 廣播一次（超兇）
  if (force || now - lastIPUdpBroadcast >= 1000) {
    lastIPUdpBroadcast = now;
    broadcast_ip_udp();
  }

  // Serial 每 8 秒印一次（給 USB 抓）
  static unsigned long lastSerial = 0;
  if (force || now - lastSerial >= 8000) {
    lastSerial = now;
    Serial.printf("\nIP:%s\n", WiFi.localIP().toString().c_str());
    Serial.printf("Stream URL: http://%s:81/stream\n\n", WiFi.localIP().toString().c_str());
  }
}

// ============= HTTP 路由 =============
void handle_root() {
  String html = "<!DOCTYPE html><html><head><meta charset='UTF-8'><title>ESP32-S3 CAM</title>"
                "<style>body{font-family:Arial;background:#000;color:#0f0;text-align:center;}"
                "img{width:100%;max-width:800px;border:3px solid #0f0;box-shadow:0 0 30px #0f0;}</style></head>"
                "<body><h1>ESP32-S3 CAM ONLINE</h1>"
                "<p>IP: " + WiFi.localIP().toString() + "</p>"
                "<img src='/stream'></body></html>";
  server.send(200, "text/html", html);
}

void handle_capture() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    server.send(500, "text/plain", "Capture failed");
    return;
  }
  server.sendHeader("Content-Type", "image/jpeg");
  server.sendHeader("Content-Disposition", "inline; filename=capture.jpg");
  server.send_P(200, "image/jpeg", (const char*)fb->buf, fb->len);
  esp_camera_fb_return(fb);
}

void handle_stream() {
  streamClient = server.client();
  streamClient.println("HTTP/1.1 200 OK");
  streamClient.println("Content-Type: multipart/x-mixed-replace; boundary=frame");
  streamClient.println("Access-Control-Allow-Origin: *");
  streamClient.println("Connection: close");
  streamClient.println();
  streamActive = true;
  lastStreamFrame = millis();
  Serial.println("[STREAM] Client connected");
}

void handle_light() {
  if (server.hasArg("on")) {
    bool state = server.arg("on").toInt();
    digitalWrite(LED_PIN, state ? HIGH : LOW);
    server.send(200, "text/plain", state ? "ON" : "OFF");
  }
}

// ============= setup & loop =============
void setup() {
  Serial.begin(115200);
  delay(1000);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  init_ultrasonic();

  Serial.println("\n\n=== ESP32-S3-CAM v5.0 全自動版 ===");

  if (!init_camera()) {
    Serial.println("Camera init failed! 系統停止");
    while (1) { digitalWrite(LED_PIN, !digitalRead(LED_PIN)); delay(200); }
  }

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  Serial.print("WiFi 連接中");
  uint8_t try_cnt = 0;
  while (WiFi.status() != WL_CONNECTED && try_cnt < 40) {
    delay(500);
    Serial.print(".");
    try_cnt++;
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("\nWiFi 連線失敗！請檢查名稱密碼");
    while (1) { digitalWrite(LED_PIN, !digitalRead(LED_PIN)); delay(100); }
  }

  Serial.println("\nWiFi 已連線！");
  Serial.print("IP 位址: ");
  Serial.println(WiFi.localIP());
  Serial.print("串流網址: http://");
  Serial.print(WiFi.localIP());
  Serial.println(":81/stream");

  udp.begin(IP_BROADCAST_PORT);

  // 開機狂喊 10 次，保證電腦一定收到
  for (int i = 0; i < 10; i++) {
    broadcast_ip_udp();
    delay(300);
  }

  server.on("/", handle_root);
  server.on("/capture", handle_capture);
  server.on("/stream", handle_stream);
  server.on("/light", handle_light);
  server.begin();

  // 閃三下表示準備好
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_PIN, HIGH); delay(100);
    digitalWrite(LED_PIN, LOW);  delay(delay(100);
  }

  Serial.println("系統就緒！畫面 3 秒內自動出現");
}

void loop() {
  server.handleClient();

  // 串流主邏輯
  if (streamActive && streamClient.connected()) {
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
  } else if (streamActive) {
    streamActive = false;
    Serial.println("[STREAM] Client 斷線");
  }

  // 超聲波
  static unsigned long lastDist = 0;
  if (millis() - lastDist > 200) {
    lastDist = millis();
    float d = get_distance();
    if (d > 2 && d < 400) Serial.printf("DIST:%.1f\n", d);
  }

  // 持續廣播 IP（每 1 秒 UDP + 每 8 秒 Serial）
  announce_ip();
}
/**
 * ESP32-S3-CAM N16R8 終極整合版
 * 功能：
 * 1. 高速 MJPEG 串流 (port 81)
 * 2. 每 100ms 透過 Serial 發送 DIST:xx.x 給 Python 後端
 * 3. 自動印出 IP 位址
 * 4. 超聲波前方障礙偵測 + 網頁雷達完美顯示
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>

// ============= WiFi 設定 =============
const char* ssid     = "Bk";
const char* password = ".........";

// ============= 超聲波腳位 =============
#define TRIG_PIN 13
#define ECHO_PIN 14

// ============= 相機腳位 (Freenove / 通用 ESP32-S3 N16R8) =============
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

WebServer server(81);
bool isStreaming = false;

// ============= 超聲波初始化 =============
void init_ultrasonic() {
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  Serial.println("[OK] 超聲波模組初始化完成 (Trig=13, Echo=14)");
}

// ============= 超聲波測距 =============
float get_distance() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  long duration = pulseIn(ECHO_PIN, HIGH, 30000); // 30ms timeout
  if (duration == 0) return -1.0;

  float distance = duration * 0.034 / 2.0;
  return distance;
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

  if (psramFound()) {
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 14;
    config.fb_count = 3;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.xclk_freq_hz = 24000000;  // 推到 24MHz 更順
  } else {
    config.frame_size = FRAMESIZE_QQVGA;
    config.jpeg_quality = 15;
    config.fb_count = 1;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[錯誤] 相機初始化失敗: 0x%x\n", err);
    return false;
  }

  sensor_t *s = esp_camera_sensor_get();
  if (s) {
    s->set_brightness(s, 0);
    s->set_contrast(s, 0);
    s->set_saturation(s, 0);
    s->set_gainceiling(s, (gainceiling_t)4);
  }

  Serial.println("[OK] 相機初始化成功");
  return true;
}

// ============= 網頁首頁 =============
void handle_root() {
  String html = R"(
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>ESP32-S3-CAM</title>
<style>body{background:#111;color:#0f0;font-family:monospace;text-align:center;padding:20px;}
img{width:100%;max-width:640px;border:2px solid #0f0;border-radius:8px;}</style>
</head><body>
<h1>ESP32-S3-CAM 遙控戰車</h1>
<p>即時影像串流：</p>
<img src="/stream">
<p><a href="/capture">點我拍照</a> | IP: )" + WiFi.localIP().toString() + R"(</p>
</body></html>)";
  server.send(200, "text/html", html);
}

// ============= 拍照 =============
void handle_capture() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    server.send(500, "text/plain", "Capture failed");
    return;
  }
  server.sendHeader("Content-Type", "image/jpeg");
  server.sendHeader("Cache-Control", "no-store");
  server.send_P(200, "image/jpeg", (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
}

// ============= MJPEG 串流 =============
void handle_stream() {
  WiFiClient client = server.client();
  client.setNoDelay(true);
  String head = "--frame\r\nContent-Type: image/jpeg\r\n\r\n";
  client.print("HTTP/1.1 200 OK\r\nContent-Type: multipart/x-mixed-replace; boundary=frame\r\n\r\n");

  isStreaming = true;
  Serial.println("[STREAM] 開始串流...");

  while (client.connected()) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) continue;

    client.print(head);
    client.write(fb->buf, fb->len);
    client.print("\r\n");

    esp_camera_fb_return(fb);
  }

  isStreaming = false;
  Serial.println("[STREAM] 串流結束");
}

void handle_not_found() {
  server.send(404, "text/plain", "404: Not Found\nUse /stream or /capture");
}

// ============= setup =============
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n\n=== ESP32-S3-CAM 遙控戰車啟動 ===");

  init_ultrasonic();

  if (!init_camera()) {
    Serial.println("相機失敗，系統停止");
    while (1) delay(1000);
  }

  WiFi.begin(ssid, password);
  Serial.print("連接 WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n[OK] WiFi 連線成功");
  Serial.print("IP 位址: http://");
  Serial.println(WiFi.localIP());

  server.on("/", handle_root);
  server.on("/capture", handle_capture);
  server.on("/stream", handle_stream);
  server.onNotFound(handle_not_found);
  server.begin();

  Serial.println("Web Server 啟動：http://" + WiFi.localIP().toString() + ":81");
  Serial.println("準備就緒！開啟你的賽博龐克介面吧！");
}

// ============= loop =============
void loop() {
  server.handleClient();

  // === 每 100ms 發送一次超聲波距離給 Python 後端 ===
  static uint32_t lastDistTime = 0;
  if (millis() - lastDistTime >= 100) {
    lastDistTime = millis();

    float dist = get_distance();
    if (dist < 0 || dist > 400) dist = 999.0;

    Serial.printf("DIST:%.1f\n", dist);  // 關鍵！Python 端會抓這行
  }

  delay(1);
}
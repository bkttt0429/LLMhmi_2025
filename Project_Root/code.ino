/**
 * ESP32-S3-CAM 韌體 v4.1（串流優化版）
 * 修復：確保 /stream 路徑穩定，增強 IP 廣播
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include <esp_now.h>

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
#define LED_PIN           48

// ============= 全域變數 =============
WebServer server(81);
WiFiClient streamClient;
bool streamActive = false;
unsigned long lastStreamFrame = 0;
const uint16_t TARGET_FPS_INTERVAL_MS = 50; // 20 FPS
uint8_t car_mac[6] = {0}; // 車子的 MAC 地址

// ============= 超聲波 =============
void init_ultrasonic() {
  pinMode(SIG_PIN, INPUT_PULLDOWN);
  digitalWrite(SIG_PIN, LOW);
  Serial.println("[OK] Ultrasonic initialized on GPIO 21");
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

  if (psramFound()) {
    Serial.println("[INFO] PSRAM detected, using VGA @ Q20");
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 20;
    config.fb_count = 2;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.grab_mode = CAMERA_GRAB_LATEST;

    if (esp_camera_init(&config) == ESP_OK) {
      Serial.println("[OK] Camera init success (PSRAM mode)");
      
      // 調整畫質設定
      sensor_t * s = esp_camera_sensor_get();
      if (s) {
        s->set_brightness(s, 0);     // -2 to 2
        s->set_contrast(s, 0);       // -2 to 2
        s->set_saturation(s, 0);     // -2 to 2
        s->set_whitebal(s, 1);       // 啟用自動白平衡
        s->set_awb_gain(s, 1);       // 啟用 AWB gain
        s->set_wb_mode(s, 0);        // 0 = auto
        s->set_exposure_ctrl(s, 1);  // 啟用自動曝光
        s->set_aec2(s, 0);           // 關閉 DSP
        s->set_gain_ctrl(s, 1);      // 啟用 AGC
        s->set_agc_gain(s, 0);       // AGC gain
        s->set_bpc(s, 0);            // 關閉黑點校正
        s->set_wpc(s, 1);            // 啟用白點校正
        s->set_raw_gma(s, 1);        // 啟用 gamma
        s->set_lenc(s, 1);           // 啟用鏡頭校正
        s->set_hmirror(s, 0);        // 水平翻轉
        s->set_vflip(s, 0);          // 垂直翻轉
        Serial.println("[OK] Camera settings optimized");
      }
      return true;
    }
    Serial.println("[WARN] PSRAM init failed, de-initializing...");
    esp_camera_deinit();
  } else {
    Serial.println("[WARN] No PSRAM detected");
  }

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

// ============= ESP-NOW 回調 =============
void onDataRecv(const uint8_t *mac, const uint8_t *data, int len) {
  if (len > 0) {
    char cmd = (char)data[0];
    Serial.printf("[ESPNOW] Received: %c from CAR\n", cmd);
    
    // 這裡可以處理來自車子的反饋（如感測器數據）
  }
}

// ============= HTTP Handlers =============
void handle_root() {
  String html = R"(
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ESP32-S3 CAM</title>
  <style>
    body { margin: 0; background: #000; color: #0f0; font-family: monospace; }
    .container { max-width: 800px; margin: 20px auto; padding: 20px; }
    h1 { text-align: center; color: #0f0; text-shadow: 0 0 10px #0f0; }
    img { width: 100%; border: 2px solid #0f0; box-shadow: 0 0 20px #0f0; }
    .info { background: #111; padding: 10px; margin: 10px 0; border: 1px solid #0f0; }
    a { color: #0ff; text-decoration: none; }
    a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <div class="container">
    <h1>📹 ESP32-S3 CAM ONLINE</h1>
    <div class="info">
      <p>📡 Stream URL: <a href="/stream" target="_blank">http://)";
  html += WiFi.localIP().toString();
  html += R"(:81/stream</a></p>
      <p>📸 Capture: <a href="/capture" target="_blank">/capture</a></p>
      <p>💡 Light: <a href="/light?on=1">ON</a> | <a href="/light?on=0">OFF</a></p>
    </div>
    <img src="/stream" alt="Loading stream..." />
  </div>
</body>
</html>
)";
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
  if (!streamClient.connected()) {
    Serial.println("[STREAM] Client connection failed");
    return;
  }
  
  streamClient.setNoDelay(true);
  streamClient.setTimeout(3000);
  
  // 發送 HTTP 標頭
  streamClient.println("HTTP/1.1 200 OK");
  streamClient.println("Content-Type: multipart/x-mixed-replace; boundary=frame");
  streamClient.println("Access-Control-Allow-Origin: *");
  streamClient.println("Connection: close");
  streamClient.println();
  
  streamActive = true;
  lastStreamFrame = 0;
  Serial.println("[STREAM] Started @20FPS");
  Serial.printf("[STREAM] Client IP: %s\n", streamClient.remoteIP().toString().c_str());
}

void handle_light() {
  if (server.hasArg("on")) {
    int state = server.arg("on").toInt();
    digitalWrite(LED_PIN, state ? HIGH : LOW);
    server.send(200, "text/plain", state ? "Light ON" : "Light OFF");
    Serial.printf("[LIGHT] %s\n", state ? "ON" : "OFF");
  } else {
    server.send(400, "text/plain", "Missing parameter: on");
  }
}

// ============= Setup & Loop =============
void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(false);
  delay(1000);

  // LED 初始化
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  Serial.println("\n=== ESP32-S3-CAM v4.1 (Optimized) ===");
  init_ultrasonic();

  if (!init_camera()) {
    Serial.println("❌ Camera FATAL ERROR! System halted.");
    while(1) {
      digitalWrite(LED_PIN, !digitalRead(LED_PIN));
      delay(200);
    }
  }

  // WiFi 連線
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  Serial.print("⏳ WiFi connecting");
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("\n❌ WiFi connection failed!");
    while(1) {
      digitalWrite(LED_PIN, !digitalRead(LED_PIN));
      delay(100);
    }
  }
  
  Serial.println("\n✓ WiFi Connected!");
  Serial.printf("📡 IP Address: %s\n", WiFi.localIP().toString().c_str());
  Serial.printf("📡 MAC Address: %s\n", WiFi.macAddress().c_str());
  Serial.printf("📹 Stream URL: http://%s:81/stream\n", WiFi.localIP().toString().c_str());

  // 初始化 ESP-NOW（用於與車子通訊）
  if (esp_now_init() == ESP_OK) {
    esp_now_register_recv_cb(onDataRecv);
    Serial.println("[ESPNOW] Initialized");
  } else {
    Serial.println("[ESPNOW] Init failed (non-critical)");
  }

  // 註冊路由
  server.on("/", handle_root);
  server.on("/capture", handle_capture);
  server.on("/stream", handle_stream);
  server.on("/light", handle_light);
  server.begin();

  Serial.println("✓ System Ready!");
  
  // 閃爍 LED 表示就緒
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(100);
    digitalWrite(LED_PIN, LOW);
    delay(100);
  }
}

void loop() {
  server.handleClient();

  // 處理串流
  if (streamActive) {
    if (!streamClient.connected()) {
      streamActive = false;
      streamClient.stop();
      Serial.println("[STREAM] Client disconnected");
    } else {
      unsigned long now = millis();
      if (now - lastStreamFrame >= TARGET_FPS_INTERVAL_MS) {
        lastStreamFrame = now;
        camera_fb_t *fb = esp_camera_fb_get();
        if (fb) {
          // 發送 MIME multipart frame
          streamClient.printf("--frame\r\n");
          streamClient.printf("Content-Type: image/jpeg\r\n");
          streamClient.printf("Content-Length: %u\r\n\r\n", fb->len);
          
          // 分段發送避免緩衝區溢出
          size_t sent = 0;
          size_t chunk_size = 1024;
          while (sent < fb->len) {
            size_t to_send = min(chunk_size, fb->len - sent);
            streamClient.write(fb->buf + sent, to_send);
            sent += to_send;
          }
          
          streamClient.print("\r\n");
          esp_camera_fb_return(fb);
        } else {
          Serial.println("[STREAM] Frame capture failed");
        }
      }
    }
  }

  // 定期回報距離數據
  static unsigned long lastDist = 0;
  if (millis() - lastDist >= 200) {
    lastDist = millis();
    float d = get_distance();
    if (d > 2.0 && d < 400.0) {
      Serial.printf("DIST:%.1f\n", d);
    }
  }

  // 定期廣播 IP（方便 PC 端自動偵測）
  static unsigned long lastIPBroadcast = 0;
  if (millis() - lastIPBroadcast >= 5000) {
    lastIPBroadcast = millis();
    Serial.printf("IP:%s\n", WiFi.localIP().toString().c_str());
  }
}
/**
 * ESP32-S3-CAM N16R8 終極整合版 (包含 HTTP 遙控轉發功能)
 * 功能：
 * 1. 影像串流 (Web Server)
 * 2. 超聲波測距 (GPIO 21, 單線模式)
 * 3. [新增] 接收 Serial 指令並透過 WiFi 轉發給 ESP8266 車子
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h> // [新增] 用於發送 HTTP 請求給車子

// ============= WiFi 設定 =============
const char* ssid     = "Bk";        // 請確認您的 WiFi 名稱
const char* password = "........."; // 請確認您的 WiFi 密碼

// ============= 遙控車設定 [新增] =============
String carIP = "boebot.local";  // 車子的 IP，預設使用 mDNS 名稱，也可改為 "192.168.x.x"
const int CAR_PORT = 80;

// ============= 超聲波腳位 (修正為 21) =============
#define SIG_PIN 21

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
#define PCLK_GPIO_NUM     13

WebServer server(81);
bool isStreaming = false;

// ============= [新增] 轉發指令到 ESP8266 車子 =============
void forwardCommandToCar(char cmd) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[FORWARD] WiFi not connected!");
    return;
  }

  // 組合 URL: http://boebot.local/cmd?act=F
  String url = "http://" + carIP + "/cmd?act=" + String(cmd);
  
  HTTPClient http;
  http.setTimeout(500);  // 設定 500ms 超時，避免卡住太久
  
  // 開始連線
  if (http.begin(url)) {
    int httpCode = http.GET(); // 發送 GET 請求
    
    if (httpCode > 0) {
      Serial.printf("[FORWARD] ✅ Sent '%c' to car (Code: %d)\n", cmd, httpCode);
    } else {
      Serial.printf("[FORWARD] ❌ Failed to send '%c' (Error: %s)\n", cmd, http.errorToString(httpCode).c_str());
    }
    http.end(); // 結束連線
  } else {
    Serial.println("[FORWARD] ❌ Unable to connect to car");
  }
}

// ============= 超聲波初始化 (單線模式) =============
void init_ultrasonic() {
  pinMode(SIG_PIN, INPUT_PULLDOWN); 
  digitalWrite(SIG_PIN, LOW);         
  Serial.println("[OK] 超聲波模組初始化完成");
}

// ============= 超聲波測距 =============
float get_distance() {
  unsigned long duration;
  
  pinMode(SIG_PIN, OUTPUT);
  digitalWrite(SIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(SIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(SIG_PIN, LOW);

  pinMode(SIG_PIN, INPUT_PULLUP);
  
  duration = pulseIn(SIG_PIN, HIGH, 30000);
  
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

  if (psramFound()) {
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 14;
    config.fb_count = 2;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.grab_mode = CAMERA_GRAB_LATEST;
  } else {
    config.frame_size = FRAMESIZE_QQVGA;
    config.jpeg_quality = 15;
    config.fb_count = 1;
  }

  if (esp_camera_init(&config) != ESP_OK) {
    return false;
  }
  return true;
}

// ============= Web Server 處理函數 =============
void handle_root() {
  String html = R"(<!DOCTYPE html><html><head><meta charset="utf-8"><title>ESP32-S3-CAM</title>
<style>body{background:#111;color:#0f0;font-family:monospace;text-align:center;padding:20px;}
img{width:100%;max-width:640px;border:2px solid #0f0;border-radius:8px;}
.btn{background:#333;color:#fff;padding:10px 20px;text-decoration:none;border:1px solid #fff;border-radius:5px;}
</style></head><body><h1>ESP32-S3-CAM 遙控戰車</h1>
<p>即時影像串流：</p><img src="/stream" id="stream"><br><br>
<p><a href="/capture" class="btn">📷 拍照</a> <a href="/stream" class="btn">📺 全螢幕串流</a></p>
<script>document.getElementById('stream').onerror=function(){this.style.display='none';setTimeout(()=>{this.src='/stream?t='+new Date().getTime();this.style.display='block';},1000);};</script>
</body></html>)";
  server.send(200, "text/html", html);
}

void handle_capture() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) { server.send(500, "text/plain", "Capture failed"); return; }
  server.sendHeader("Content-Type", "image/jpeg");
  server.sendHeader("Content-Disposition", "inline; filename=capture.jpg");
  server.send_P(200, "image/jpeg", (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
}

void handle_stream() {
  WiFiClient client = server.client();
  client.setNoDelay(true);
  String response = "HTTP/1.1 200 OK\r\nContent-Type: multipart/x-mixed-replace; boundary=frame\r\n\r\n";
  client.print(response);
  isStreaming = true;
  while (client.connected()) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) { delay(10); continue; }
    client.print("--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + String(fb->len) + "\r\n\r\n");
    client.write(fb->buf, fb->len);
    client.print("\r\n");
    esp_camera_fb_return(fb);
    delay(1);
  }
  isStreaming = false;
}

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(false);
  
  init_ultrasonic();

  if (!init_camera()) {
    Serial.println("❌ 相機初始化失敗！");
    while (1) delay(1000);
  }

  WiFi.begin(ssid, password);
  Serial.print("Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  
  Serial.println("\n[OK] WiFi Connected");
  Serial.print("Camera IP: http://"); Serial.println(WiFi.localIP());
  Serial.print("Car Target: http://"); Serial.println(carIP);

  server.on("/", handle_root);
  server.on("/capture", handle_capture);
  server.on("/stream", handle_stream);
  server.begin();
}

void loop() {
  server.handleClient();

  // 1. [新增] 處理來自電腦 Serial 的指令 -> 轉發給車子
  if (Serial.available() > 0) {
    char cmd = Serial.read();
    
    // 忽略換行符號
    if (cmd != '\n' && cmd != '\r') {
      // 判斷是否為有效指令 (F/B/L/R/S)
      if (cmd == 'F' || cmd == 'B' || cmd == 'L' || cmd == 'R' || cmd == 'S') {
        forwardCommandToCar(cmd);
      }
      // 這裡也可以加入邏輯來處理 "CAR_IP:192.168.x.x" 的字串設定
    }
  }

  // 2. 超聲波測距邏輯 (每 100ms)
  static unsigned long lastDistTime = 0;
  if (millis() - lastDistTime >= 100) {
    lastDistTime = millis();
    float dist = get_distance();
    if (dist > 2.0 && dist < 400.0) {
      Serial.printf("DIST:%.1f\n", dist);
    }
  }
  
  delay(1);
}
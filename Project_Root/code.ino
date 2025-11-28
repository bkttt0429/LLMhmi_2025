/**
 * ESP32-S3-CAM N16R8 終極整合版 (修正腳位衝突版)
 * 修正說明：
 * 1. 將超聲波腳位改為 GPIO 21 (單線模式)，避開相機的 GPIO 13
 * 2. 整合單線驅動邏輯 (One-wire Mode)
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>

// ============= WiFi 設定 =============
const char* ssid     = "Bk";      // 請確認您的 WiFi 名稱
const char* password = "........."; // 請確認您的 WiFi 密碼

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
#define PCLK_GPIO_NUM     13  // 相機專用，絕對不能跟超聲波共用！

WebServer server(81);
bool isStreaming = false;

// ============= 超聲波初始化 (單線模式) =============
void init_ultrasonic() {
  pinMode(SIG_PIN, INPUT); // 預設為輸入，避免干擾
  Serial.println("[OK] 超聲波模組初始化完成 (SIG=GPIO 21)");
}

// ============= 超聲波測距 (單線模式邏輯) =============
float get_distance() {
  unsigned long duration;
  float distance;

  // 1. 切換為 OUTPUT 發送 Trigger
  pinMode(SIG_PIN, OUTPUT);
  digitalWrite(SIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(SIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(SIG_PIN, LOW);

  // 2. 切換為 INPUT 接收 Echo
  pinMode(SIG_PIN, INPUT);
  
  // 3. 讀取脈衝 (Timeout 30ms)
  duration = pulseIn(SIG_PIN, HIGH, 30000); 

  if (duration == 0) {
    return -1.0; // 超時或無訊號
  }

  // 4. 計算距離
  distance = duration * 0.034 / 2.0;
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
    config.fb_count = 2; // 稍微減少緩衝區數量，釋放記憶體給系統
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.grab_mode = CAMERA_GRAB_LATEST;
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
    s->set_framesize(s, FRAMESIZE_VGA); // 確保解析度
    s->set_brightness(s, 1); // 稍微調亮
    s->set_saturation(s, 0);
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
img{width:100%;max-width:640px;border:2px solid #0f0;border-radius:8px;}
.btn{background:#333;color:#fff;padding:10px 20px;text-decoration:none;border:1px solid #fff;border-radius:5px;}
</style>
</head><body>
<h1>ESP32-S3-CAM 遙控戰車</h1>
<p>即時影像串流：</p>
<img src="/stream" id="stream">
<br><br>
<p>
  <a href="/capture" class="btn">📷 拍照</a> 
  <a href="/stream" class="btn">📺 全螢幕串流</a>
</p>
<p id="ip">IP: )" + WiFi.localIP().toString() + R"(</p>
<script>
  // 斷線自動重連影像
  document.getElementById('stream').onerror = function() {
    this.style.display = 'none';
    setTimeout(() => {
      this.src = '/stream?t=' + new Date().getTime();
      this.style.display = 'block';
    }, 1000);
  };
</script>
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
  server.sendHeader("Content-Disposition", "inline; filename=capture.jpg");
  server.send_P(200, "image/jpeg", (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
}

// ============= MJPEG 串流 =============
void handle_stream() {
  WiFiClient client = server.client();
  client.setNoDelay(true); // 降低延遲
  
  String response = "HTTP/1.1 200 OK\r\n";
  response += "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n\r\n";
  client.print(response);

  isStreaming = true;
  Serial.println("[STREAM] 用戶端已連接");

  while (client.connected()) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
      delay(10);
      continue;
    }

    client.print("--frame\r\n");
    client.print("Content-Type: image/jpeg\r\n");
    client.print("Content-Length: " + String(fb->len) + "\r\n\r\n");
    client.write(fb->buf, fb->len);
    client.print("\r\n");

    esp_camera_fb_return(fb);
    
    // 稍微延遲讓 CPU 有機會處理 WiFi
    // 如果想要更高 FPS 可以設為 0，但可能會卡住
    delay(1); 
  }

  isStreaming = false;
  Serial.println("[STREAM] 用戶端斷開");
}

void handle_not_found() {
  server.send(404, "text/plain", "404: Not Found");
}

// ============= setup =============
void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(false); // 減少雜訊
  delay(1000);
  Serial.println("\n\n=== ESP32-S3-CAM 啟動 (GPIO 21 Ultrasonic) ===");

  // 1. 初始化超聲波
  init_ultrasonic();

  // 2. 初始化相機
  if (!init_camera()) {
    Serial.println("❌ 相機初始化失敗！請檢查接線或電源。");
    while (1) delay(1000); // 停在這裡
  }

  // 3. 連接 WiFi
  WiFi.begin(ssid, password);
  Serial.print("正在連接 WiFi");
  
  int retry = 0;
  while (WiFi.status() != WL_CONNECTED && retry < 20) {
    delay(500);
    Serial.print(".");
    retry++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[OK] WiFi 連線成功");
    Serial.print("IP 位址: http://");
    Serial.println(WiFi.localIP());
    
    // 啟動 Web Server
    server.on("/", handle_root);
    server.on("/capture", handle_capture);
    server.on("/stream", handle_stream);
    server.onNotFound(handle_not_found);
    server.begin();
    Serial.println("Web Server 已啟動");
  } else {
    Serial.println("\n[錯誤] WiFi 連線逾時，請檢查密碼");
  }
}

// ============= loop =============
void loop() {
  server.handleClient();

  // 每 100ms 測距並回傳給 Python
  static unsigned long lastDistTime = 0;
  if (millis() - lastDistTime >= 100) {
    lastDistTime = millis();

    float dist = get_distance();
    
    // 簡單過濾無效值 (小於 2cm 或大於 400cm 視為無效)
    if (dist > 2.0 && dist < 400.0) {
      Serial.printf("DIST:%.1f\n", dist);
    } else {
       // 讀取錯誤時也可以傳送，或選擇不傳送
       // Serial.println("DIST:-1.0"); 
    }
  }
  
  // 讓 CPU 休息一下，避免 Watchdog 觸發
  delay(1);
}
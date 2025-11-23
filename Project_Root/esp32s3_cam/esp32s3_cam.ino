/**
 * ESP32-S3-CAM N16R8 專用版
 * N16R8 = 16MB Flash + 8MB PSRAM
 * 使用標準 Freenove/通用 S3-CAM 腳位配置
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include <Wire.h>

// ============= WiFi 設定 =============
const char* ssid     = "Bk";
const char* password = ".........";

// ============= ESP32-S3-CAM N16R8 專用腳位 =============
// 參考 Freenove / 通用 ESP32-S3-CAM N16R8 腳位定義

#define PWDN_GPIO_NUM     -1  // 無電源關閉腳位
#define RESET_GPIO_NUM    -1  // 無硬體重置腳位
#define XCLK_GPIO_NUM     15
#define SIOD_GPIO_NUM     4   // I2C SDA
#define SIOC_GPIO_NUM     5   // I2C SCL

// 診斷時印出來的 D0~D7 對應
#define Y9_GPIO_NUM       16  // D7
#define Y8_GPIO_NUM       17  // D6
#define Y7_GPIO_NUM       18  // D5
#define Y6_GPIO_NUM       12  // D4
#define Y5_GPIO_NUM       10  // D3
#define Y4_GPIO_NUM       8   // D2
#define Y3_GPIO_NUM       9   // D1
#define Y2_GPIO_NUM       11  // D0

#define VSYNC_GPIO_NUM    6
#define HREF_GPIO_NUM     7
#define PCLK_GPIO_NUM     13

// ============= LED 腳位（板載小燈，如無可改成 -1）============
#define LED_GPIO_NUM      2   // 若板子沒有接 2，可以註解掉 LED 相關程式

// ============= 全域變數 =============
WebServer server(81);  // 使用 81 port 當網頁伺服器

framesize_t current_frame_size = FRAMESIZE_VGA;  // 640x480
int         current_quality    = 12;             // 影像品質（數字越小品質越好）
bool        isStreaming        = false;

// ============= 工具函式：輸出 ESP32 系統資訊 =============
void print_chip_info() {
  Serial.println("\n----------------------------------------");
  Serial.println("    ESP32-S3-CAM N16R8 診斷報告        ");
  Serial.println("----------------------------------------");

  Serial.printf("晶片型號: %s\n", ESP.getChipModel());
  Serial.printf("晶片修訂版: %d\n", ESP.getChipRevision());
  Serial.printf("CPU 核心數: %d\n", ESP.getChipCores());
  Serial.printf("CPU 頻率: %d MHz\n", ESP.getCpuFreqMHz());

  Serial.printf("\n記憶體狀態:\n");
  Serial.printf("  Flash 大小: %d MB\n", ESP.getFlashChipSize() / (1024 * 1024));
  Serial.printf("  PSRAM 大小: %d MB\n", ESP.getPsramSize() / (1024 * 1024));
  Serial.printf("  可用 PSRAM: %d KB\n", ESP.getFreePsram() / 1024);
  Serial.printf("  可用 Heap: %d KB\n", ESP.getFreeHeap() / 1024);

  Serial.println("\n相機腳位配置:");
  Serial.printf("  XCLK:  GPIO%d\n", XCLK_GPIO_NUM);
  Serial.printf("  SIOD:  GPIO%d (I2C SDA)\n", SIOD_GPIO_NUM);
  Serial.printf("  SIOC:  GPIO%d (I2C SCL)\n", SIOC_GPIO_NUM);
  Serial.printf("  PCLK:  GPIO%d\n", PCLK_GPIO_NUM);
  Serial.printf("  VSYNC: GPIO%d\n", VSYNC_GPIO_NUM);
  Serial.printf("  HREF:  GPIO%d\n", HREF_GPIO_NUM);
  Serial.printf("  D0:    GPIO%d\n", Y2_GPIO_NUM);
  Serial.printf("  D1:    GPIO%d\n", Y3_GPIO_NUM);
  Serial.printf("  D2:    GPIO%d\n", Y4_GPIO_NUM);
  Serial.printf("  D3:    GPIO%d\n", Y5_GPIO_NUM);
  Serial.printf("  D4:    GPIO%d\n", Y6_GPIO_NUM);
  Serial.printf("  D5:    GPIO%d\n", Y7_GPIO_NUM);
  Serial.printf("  D6:    GPIO%d\n", Y8_GPIO_NUM);
  Serial.printf("  D7:    GPIO%d\n", Y9_GPIO_NUM);
  Serial.println("----------------------------------------\n");
}

// ============= 相機初始化（把你原本的 config.* 全搬進來）============
bool init_camera() {
  camera_config_t config;
  memset(&config, 0, sizeof(config));

  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;

  // D0~D7
  config.pin_d0       = Y2_GPIO_NUM;  // 11
  config.pin_d1       = Y3_GPIO_NUM;  // 9
  config.pin_d2       = Y4_GPIO_NUM;  // 8
  config.pin_d3       = Y5_GPIO_NUM;  // 10
  config.pin_d4       = Y6_GPIO_NUM;  // 12
  config.pin_d5       = Y7_GPIO_NUM;  // 18
  config.pin_d6       = Y8_GPIO_NUM;  // 17
  config.pin_d7       = Y9_GPIO_NUM;  // 16

  // sync & clock
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;

  // SCCB / I2C
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;

  // PWDN / RESET
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;

  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // PSRAM 設定
// PSRAM 設定 (N16R8 專屬優化)
  if (psramFound()) {
    config.frame_size   = FRAMESIZE_VGA;    // 6handle_stream()40x480
    config.jpeg_quality = 14;               // [優化] 改為 14-20 (原本12)，數字越大檔案越小，FPS越高
    config.fb_count     = 3;                // [優化] 改為 3 或 4 (原本2)，利用 8MB PSRAM 做三倍緩衝
    config.fb_location  = CAMERA_FB_IN_PSRAM;
    
    // [優化] 嘗試提升 XCLK 到 24MHz (若畫面出現條紋或不穩，請改回 20000000)
    config.xclk_freq_hz = 24000000;
  } else {
    config.frame_size   = FRAMESIZE_QQVGA;        // 160x120，保險一點
    config.jpeg_quality = 15;
    config.fb_count     = 1;
    config.fb_location  = CAMERA_FB_IN_DRAM;
  }

  Serial.println("\n[INFO] 開始初始化相機...");
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[錯誤] Camera init failed: 0x%x\n", err);
    return false;
  }

  Serial.println("[OK] Camera init success.");

  // 可選：調整 sensor 參數
  sensor_t * s = esp_camera_sensor_get();
  if (s) {
    s->set_brightness(s, 0);    // -2 ~ 2
    s->set_contrast(s, 0);      // -2 ~ 2
    s->set_saturation(s, 0);    // -2 ~ 2
    s->set_gainceiling(s, GAINCEILING_4X);
    // s->set_framesize(s, FRAMESIZE_VGA); // 如需改畫面大小
  }

  return true;
}

// ============= HTTP 回應：主畫面 =============
void handle_root() {
  String html =
    "<!DOCTYPE html>"
    "<html lang='zh-TW'>"
    "<head>"
    "<meta charset='UTF-8'>"
    "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
    "<title>ESP32-S3-CAM 控制介面</title>"
    "<style>"
    "body { font-family: Arial, sans-serif; background: #111; color: #eee; text-align: center; }"
    "h1 { margin-top: 10px; }"
    ".container { max-width: 800px; margin: auto; }"
    "button { padding: 8px 16px; margin: 4px; font-size: 14px; cursor: pointer; }"
    ".info { margin-top: 10px; font-size: 14px; color: #aaa; }"
    "img { width: 100%; max-width: 640px; border: 2px solid #444; border-radius: 4px; margin-top: 10px; }"
    "</style>"
    "</head>"
    "<body>"
    "<div class='container'>"
      "<h1>ESP32-S3-CAM N16R8 控制介面</h1>"
      "<div>"
        "<button onclick=\"location.href='/capture'\">拍照（單張）</button>"
        "<button onclick=\"location.href='/stream'\">開始影像串流</button>"
      "</div>"
      "<div class='info'>"
        "<p>串流路徑：<code>/stream</code></p>"
        "<p>單張拍照：<code>/capture</code></p>"
      "</div>"
      "<img src='/capture' alt='Camera Image'>"
    "</div>"
    "</body>"
    "</html>";

  server.send(200, "text/html", html);
}

// ============= 拍照 /capture =============
void handle_capture() {
  camera_fb_t * fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("[錯誤] 無法從相機取得影像");
    server.send(500, "text/plain", "Camera capture failed");
    return;
  }

  server.sendHeader("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0");
  server.sendHeader("Pragma", "no-cache");
  server.sendHeader("Expires", "-1");
  server.setContentLength(fb->len);
  server.send(200, "image/jpeg", "");
  WiFiClient client = server.client();
  client.write(fb->buf, fb->len);

  esp_camera_fb_return(fb);
}

// ============= 影像串流 /stream =============
void handle_stream() {
  WiFiClient client = server.client();

  // [優化] 啟用 TCP NoDelay，減少網路延遲
  client.setNoDelay(true);

  String response =
    "HTTP/1.1 200 OK\r\n"
    "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n"
    "Access-Control-Allow-Origin: *\r\n"  // 允許跨域，方便瀏覽器測試
    "Connection: close\r\n"
    "\r\n";
  client.print(response);

  isStreaming = true;
  Serial.println("[INFO] 開始高速 MJPEG 串流...");

  // 用來計算 FPS
  long lastTime = millis();
  int frameCount = 0;

  while (client.connected()) {
    camera_fb_t * fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("[錯誤] 無法從相機取得影像 (stream)");
      break;
    }

    // 傳送標頭
    client.print("--frame\r\n");
    client.print("Content-Type: image/jpeg\r\n");
    client.print("Content-Length: " + String(fb->len) + "\r\n\r\n");
    
    // 傳送影像數據
    // ESP32-S3 的 WiFi stack 處理大封包能力不錯，直接 write 即可
    client.write(fb->buf, fb->len);
    
    // 傳送結尾
    client.print("\r\n");

    // 釋放 buffer 給下一幀使用
    esp_camera_fb_return(fb);

    // [優化] 移除 delay(30); 讓它全速跑！
    // 只有在過熱或需要限制頻寬時才加 delay
    
    // --- 簡易 FPS 計算 (每秒印出一次) ---
    frameCount++;
    long now = millis();
    if (now - lastTime > 1000) {
      float fps = frameCount * 1000.0 / (now - lastTime);
      Serial.printf("[Stream] FPS: %.2f / Size: %u bytes\n", fps, fb->len);
      lastTime = now;
      frameCount = 0;
    }
  }

  isStreaming = false;
  Serial.println("[INFO] 串流結束。");
}
// ============= Not Found =============
void handle_not_found() {
  String message = "錯誤: 找不到此路徑\n\n";
  message += "請使用以下路徑:\n";
  message += "  /           : 主頁面\n";
  message += "  /capture    : 拍照\n";
  message += "  /stream     : 影像串流\n";
  server.send(404, "text/plain", message);
}

// ============= setup =============
void setup() {
  Serial.begin(115200);
  delay(1000);

#ifdef LED_GPIO_NUM
  pinMode(LED_GPIO_NUM, OUTPUT);
  digitalWrite(LED_GPIO_NUM, LOW);
#endif

  Serial.println("\n----------------------------------------");
  Serial.println(" ESP32-S3-CAM N16R8 啟動中...");
  Serial.println("----------------------------------------");

  print_chip_info();

  if (!init_camera()) {
    Serial.println("[錯誤] 相機初始化失敗，請檢查接線或板子型號設定");
    while (true) {
      delay(1000);
    }
  }

  Serial.println("\n[INFO] 開始連接 WiFi...");
  WiFi.begin(ssid, password);

  int retry = 0;
  while (WiFi.status() != WL_CONNECTED && retry < 30) {
    delay(500);
    Serial.print(".");
    retry++;
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("\n[錯誤] WiFi 連線失敗，請確認 SSID/密碼或 AP 狀態");
  } else {
    Serial.println("\n[OK] WiFi 連線成功");
    Serial.print("IP 位址: ");
    Serial.println(WiFi.localIP());
  }

  server.on("/",        handle_root);
  server.on("/capture", handle_capture);
  server.on("/stream",  handle_stream);
  server.onNotFound(handle_not_found);
  server.begin();

  Serial.println("\n--------------------------------------------");
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("  [WEB] 網頁介面:   http://%s:81        \n", WiFi.localIP().toString().c_str());
    Serial.printf("  [VIDEO] 影像串流: http://%s:81/stream \n", WiFi.localIP().toString().c_str());
    Serial.printf("  [PHOTO] 單張拍照: http://%s:81/capture\n", WiFi.localIP().toString().c_str());
  }
  Serial.println("--------------------------------------------");
  Serial.println("\n[完成] 系統啟動完成，準備接收連線...\n");
}

// ============= loop =============
void loop() {
  server.handleClient();
  delay(1);
}

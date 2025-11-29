/**
 * ESP32-S3-CAM N16R8 終極整合版 (非阻塞式轉發)
 * 修正：使用獨立任務處理 HTTP 轉發，避免阻塞主迴圈
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include <esp_now.h>
#include <WebSocketsServer.h>

// ============= WiFi 設定 =============
const char* ssid     = "Bk";
const char* password = ".........";

// ============= 遙控車設定 =============
// 👉 將下面的 MAC 換成 ESP8266/12F 車子的 WiFi MAC 位址
uint8_t carPeerMac[] = {0x24, 0x6F, 0x28, 0x00, 0x00, 0x00};
const int ESPNOW_CHANNEL = 0; // 0 = 跟隨目前 WiFi 頻道

// ============= 超聲波腳位 =============
#define SIG_PIN 21

// ============= 相機腳位 =============
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
WebSocketsServer controlSocket(82);
bool isStreaming = false;
bool espNowReady = false;

// ============= [新增] 指令佇列 =============
#define CMD_QUEUE_SIZE 10
const int MAX_RETRIES = 3;
const unsigned long ACK_TIMEOUT = 250; // ms

struct CommandItem {
  char cmd;
  uint16_t seq;
  uint8_t retries;
  unsigned long lastAttempt;
  bool awaitingResponse;
};

CommandItem cmdQueue[CMD_QUEUE_SIZE];
volatile int cmdQueueHead = 0;
volatile int cmdQueueTail = 0;
volatile uint16_t cmdSequence = 1;

bool isValidCommand(char cmd) {
  return cmd == 'F' || cmd == 'B' || cmd == 'L' || cmd == 'R' || cmd == 'S' ||
         cmd == 'W' || cmd == 'w';
}

bool isValidCommand(char cmd) {
  return cmd == 'F' || cmd == 'B' || cmd == 'L' || cmd == 'R' || cmd == 'S' ||
         cmd == 'W' || cmd == 'w';
}

bool isValidCommand(char cmd) {
  return cmd == 'F' || cmd == 'B' || cmd == 'L' || cmd == 'R' || cmd == 'S' ||
         cmd == 'W' || cmd == 'w';
}

// 將指令加入佇列（非阻塞）
void queueCommand(char cmd) {
  int next = (cmdQueueHead + 1) % CMD_QUEUE_SIZE;
  if (next != cmdQueueTail) {
    cmdQueue[cmdQueueHead] = {cmd, cmdSequence++, 0, 0, false};
    cmdQueueHead = next;
  }
}

bool hasPendingCommand() {
  return cmdQueueHead != cmdQueueTail;
}

CommandItem &currentCommand() {
  return cmdQueue[cmdQueueTail];
}

void popCommand() {
  cmdQueueTail = (cmdQueueTail + 1) % CMD_QUEUE_SIZE;
}

// ============= ESP-NOW 相關 =============
void onEspNowSent(const uint8_t *mac_addr, esp_now_send_status_t status) {
  Serial.printf("[ESPNOW] Send status: %s\n", status == ESP_NOW_SEND_SUCCESS ? "OK" : "FAIL");
}

bool sendEspNow(char cmd) {
  if (!espNowReady) return false;
  esp_err_t result = esp_now_send(carPeerMac, reinterpret_cast<uint8_t *>(&cmd), 1);
  return result == ESP_OK;
}

void initEspNow() {
  if (esp_now_init() != ESP_OK) {
    Serial.println("[ESPNOW] Init failed");
    espNowReady = false;
    return;
  }

  esp_now_register_send_cb(onEspNowSent);

  esp_now_peer_info_t peerInfo = {};
  memcpy(peerInfo.peer_addr, carPeerMac, 6);
  peerInfo.channel = ESPNOW_CHANNEL == 0 ? static_cast<uint8_t>(WiFi.channel()) : ESPNOW_CHANNEL;
  peerInfo.encrypt = false;

  if (esp_now_add_peer(&peerInfo) != ESP_OK) {
    Serial.println("[ESPNOW] Add peer failed");
    espNowReady = false;
    return;
  }

  espNowReady = true;
  Serial.print("[ESPNOW] Ready on channel ");
  Serial.println(peerInfo.channel);
}

// ============= [修改] 獨立任務處理指令轉發 =============
void commandForwardTask(void *parameter) {
  while (true) {
    char cmd = dequeueCommand();

    if (cmd != 0) {
      bool sent = sendEspNow(cmd);
      Serial.printf("[FWD][ESPNOW] %s %c\n", sent ? "✓" : "✗", cmd);
    }

    vTaskDelay(10 / portTICK_PERIOD_MS); // 釋放 CPU
  }
}

// ============= WebSocket 控制通道 =============
void onWebSocketEvent(uint8_t clientNum, WStype_t type, uint8_t *payload, size_t length) {
  switch (type) {
    case WStype_DISCONNECTED:
      Serial.printf("[WS] Client %u disconnected\n", clientNum);
      break;
    case WStype_CONNECTED:
      Serial.printf("[WS] Client %u connected\n", clientNum);
      break;
    case WStype_TEXT:
      if (length > 0) {
        char cmd = static_cast<char>(payload[0]);
        if (isValidCommand(cmd)) {
          queueCommand(cmd);
        }
      }
      break;
    default:
      break;
  }
}

// ============= 超聲波初始化 =============
void init_ultrasonic() {
  pinMode(SIG_PIN, INPUT_PULLDOWN);
  digitalWrite(SIG_PIN, LOW);
  Serial.println("[OK] 超聲波模組初始化完成 (Trig=13, Echo=14)");
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

  return esp_camera_init(&config) == ESP_OK;
}

// ============= Web Server =============
void handle_root() {
  String html = R"(<!DOCTYPE html><html><head><meta charset="utf-8"><title>ESP32-S3-CAM</title>
<style>body{background:#111;color:#0f0;font-family:monospace;text-align:center;padding:20px;}
img{width:100%;max-width:640px;border:2px solid #0f0;border-radius:8px;}
.btn{background:#333;color:#fff;padding:10px 20px;text-decoration:none;border:1px solid #fff;border-radius:5px;}
</style></head><body><h1>ESP32-S3-CAM 遙控戰車</h1>
<p>即時影像串流：</p><img src="/stream" id="stream"><br><br>
<p><a href="/capture" class="btn">📷 拍照</a> <a href="/stream" class="btn">📺 全螢幕串流</a></p>
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
  // 只保留一個串流客戶端，並在 loop() 中持續餵影像以避免阻塞其他處理
  streamClient = server.client();
  streamClient.setNoDelay(true);
  streamClient.print("HTTP/1.1 200 OK\r\nContent-Type: multipart/x-mixed-replace; boundary=frame\r\n\r\n");
  streamActive = true;
  isStreaming = true;
  lastStreamFrame = 0;
  Serial.println("[STREAM] 開啟非阻塞串流");
}

// 保留 HTTP 控制端點以便相容與除錯
void handle_cmd() {
  if (!server.hasArg("act")) {
    server.send(400, "text/plain", "Missing act");
    return;
  }

  char cmd = server.arg("act").charAt(0);
  if (isValidCommand(cmd)) {
    queueCommand(cmd);
    server.send(200, "text/plain", "Queued");
  } else {
    server.send(400, "text/plain", "Invalid cmd");
  }
}

// 保留 HTTP 控制端點以便相容與除錯
void handle_cmd() {
  if (!server.hasArg("act")) {
    server.send(400, "text/plain", "Missing act");
    return;
  }

  char cmd = server.arg("act").charAt(0);
  if (isValidCommand(cmd)) {
    queueCommand(cmd);
    server.send(200, "text/plain", "Queued");
  } else {
    server.send(400, "text/plain", "Invalid cmd");
  }
}

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(false);
  Serial.println("\n=== ESP32-S3-CAM 遙控戰車啟動 ===");
  
  init_ultrasonic();

  if (!init_camera()) {
    Serial.println("[ERR] 相機初始化失敗！");
    while (1) delay(1000);
  }
  Serial.println("[OK] 相機初始化成功");

  WiFi.begin(ssid, password);
  Serial.print("連接 WiFi");
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[OK] WiFi 連線成功");
    Serial.print("IP 位址: http://");
    Serial.println(WiFi.localIP());
    Serial.print("Web Server 啟動：http://");
    Serial.print(WiFi.localIP());
    Serial.println(":81");
    Serial.println("準備就緒！開啟你的賽博龐克介面吧！");
  } else {
    Serial.println("\n[ERR] WiFi 連線失敗");
  }

  initEspNow();

  server.on("/", handle_root);
  server.on("/capture", handle_capture);
  server.on("/stream", handle_stream);
  server.on("/cmd", handle_cmd);
  server.begin();

  controlSocket.begin();
  controlSocket.onEvent(onWebSocketEvent);

  // 啟動獨立的指令轉發任務
  xTaskCreatePinnedToCore(
    commandForwardTask,   // 任務函數
    "CommandForward",     // 任務名稱
    4096,                 // Stack 大小
    NULL,                 // 參數
    1,                    // 優先級
    NULL,                 // 任務 handle
    0                     // CPU 核心 (0 或 1)
  );
}

void loop() {
  server.handleClient();
  controlSocket.loop();

  // 處理 Serial 指令（非阻塞）
  while (Serial.available() > 0) {
    char cmd = Serial.read();

    if (cmd != '\n' && cmd != '\r') {
      if (isValidCommand(cmd)) {
        queueCommand(cmd); // 加入佇列，由獨立任務處理
      }
    }
  }

  // 超聲波測距（降低頻率）
  static unsigned long lastDistTime = 0;
  if (millis() - lastDistTime >= 200) { // 改為 200ms
    lastDistTime = millis();
    float dist = get_distance();
    if (dist > 2.0 && dist < 400.0) {
      Serial.printf("DIST:%.1f\n", dist);
    }
  }
  
  vTaskDelay(1); // 釋放 CPU 給其他任務
}
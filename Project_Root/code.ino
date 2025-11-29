/**
 * ESP32-S3-CAM 韌體 v3.2 (自動降級修復版)
 * ✅ 新增：若 PSRAM 初始化失敗，自動降級為 QVGA/SRAM 模式
 * ✅ 修復：frame buffer malloc failed 導致的死機
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include <esp_now.h>
#include <mbedtls/base64.h>
#include <mbedtls/sha1.h>

// ============= WiFi 設定 =============
const char* ssid     = "Bk";        
const char* password = "........."; 

// ============= 遙控車設定 (ESP8266 MAC) =============
uint8_t carPeerMac[] = {0x24, 0x6F, 0x28, 0x00, 0x00, 0x00}; // 請確認此 MAC
const int ESPNOW_CHANNEL = 0;

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
WiFiServer wsServer(82);
WiFiClient wsClient;
WiFiClient streamClient;

bool wsHandshakeDone = false;
bool streamActive = false;
bool espNowReady = false;
unsigned long lastStreamFrame = 0;

// 指令佇列
#define CMD_QUEUE_SIZE 10
char cmdQueue[CMD_QUEUE_SIZE];
volatile int cmdHead = 0;
volatile int cmdTail = 0;

// ============= 指令處理 =============
bool isValidCommand(char cmd) {
  return cmd == 'F' || cmd == 'B' || cmd == 'L' || 
         cmd == 'R' || cmd == 'S' || cmd == 'W' || cmd == 'w';
}

void queueCommand(char cmd) {
  int next = (cmdHead + 1) % CMD_QUEUE_SIZE;
  if (next != cmdTail) {
    cmdQueue[cmdHead] = cmd;
    cmdHead = next;
  }
}

char dequeueCommand() {
  if (cmdHead == cmdTail) return 0;
  char cmd = cmdQueue[cmdTail];
  cmdTail = (cmdTail + 1) % CMD_QUEUE_SIZE;
  return cmd;
}

// ============= ESP-NOW (相容 Core 3.x) =============
void onEspNowSent(const wifi_tx_info_t *info, esp_now_send_status_t status) {
  // 發送回調，可在此加入除錯訊息
}

bool sendEspNow(char cmd) {
  if (!espNowReady) return false;
  return esp_now_send(carPeerMac, (uint8_t*)&cmd, 1) == ESP_OK;
}

void initEspNow() {
  if (esp_now_init() != ESP_OK) {
    Serial.println("[ESPNOW] Init failed");
    return;
  }
  esp_now_register_send_cb(onEspNowSent);
  
  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, carPeerMac, 6);
  peer.channel = 0;
  peer.encrypt = false;
  
  if (esp_now_add_peer(&peer) == ESP_OK) {
    espNowReady = true;
    Serial.println("[ESPNOW] Ready");
  } else {
    Serial.println("[ESPNOW] Add peer failed");
  }
}

// ============= WebSocket =============
String buildAcceptKey(const String &clientKey) {
  const char *guid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
  String combined = clientKey + guid;
  uint8_t sha1Result[20];
  mbedtls_sha1((const unsigned char*)combined.c_str(), combined.length(), sha1Result);
  size_t outLen = 0;
  unsigned char base64Result[64] = {0};
  mbedtls_base64_encode(base64Result, sizeof(base64Result), &outLen, sha1Result, sizeof(sha1Result));
  return String((char*)base64Result);
}

bool performWebSocketHandshake(WiFiClient &client) {
  unsigned long start = millis();
  String request = "";
  while (millis() - start < 1000) {
    while (client.available()) {
      request += (char)client.read();
      if (request.endsWith("\r\n\r\n")) break;
    }
    if (request.endsWith("\r\n\r\n")) break;
    delay(5);
  }
  int keyIndex = request.indexOf("Sec-WebSocket-Key:");
  if (keyIndex < 0) return false;
  int keyEnd = request.indexOf('\r', keyIndex);
  if (keyEnd < 0) return false;
  String clientKey = request.substring(keyIndex + 19, keyEnd);
  clientKey.trim();
  String acceptKey = buildAcceptKey(clientKey);
  String response = "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: " + acceptKey + "\r\n\r\n";
  client.print(response);
  return true;
}

void handleWebSocketFrames() {
  if (!wsClient || !wsClient.connected()) return;
  while (wsClient.available() >= 2) {
    uint8_t header[2];
    wsClient.read(header, 2);
    uint64_t payloadLen = header[1] & 0x7F;
    if (payloadLen == 126) {
      uint8_t ext[2];
      wsClient.read(ext, 2);
      payloadLen = (ext[0] << 8) | ext[1];
    } else if (payloadLen == 127) return;
    
    uint8_t mask[4];
    wsClient.read(mask, 4);
    for (uint64_t i = 0; i < payloadLen; i++) {
      char c = (char)(wsClient.read() ^ mask[i % 4]);
      if (i == 0 && isValidCommand(c)) queueCommand(c);
    }
  }
}

void pollWebSocketControl() {
  if (!wsClient || !wsClient.connected()) {
    wsClient.stop();
    wsHandshakeDone = false;
    WiFiClient newClient = wsServer.available();
    if (newClient) {
      wsClient = newClient;
      wsClient.setNoDelay(true);
      if (performWebSocketHandshake(wsClient)) {
        wsHandshakeDone = true;
        Serial.println("[WS] Client connected");
      }
    }
  } else if (wsHandshakeDone) {
    handleWebSocketFrames();
  }
}

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

// ============= 相機初始化 (增強版) =============
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
  
  // 嘗試使用 PSRAM
  if (psramFound()) {
    Serial.println("[INFO] PSRAM detected, trying VGA resolution...");
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 12;
    config.fb_count = 2;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.grab_mode = CAMERA_GRAB_LATEST;
    
    if (esp_camera_init(&config) == ESP_OK) {
      Serial.println("[OK] Camera init success (PSRAM mode)");
      return true;
    }
    Serial.println("[WARN] PSRAM init failed, de-initializing...");
    esp_camera_deinit(); // 初始化失敗需先釋放
  } else {
    Serial.println("[WARN] No PSRAM detected");
  }

  // 降級模式：使用內部 SRAM
  Serial.println("[INFO] Falling back to Low-Res (SRAM) mode...");
  config.frame_size = FRAMESIZE_QVGA; // 降級為 QVGA
  config.jpeg_quality = 15;
  config.fb_count = 1;                // 單緩衝
  config.fb_location = CAMERA_FB_IN_DRAM; // 使用內部 RAM
  
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
  Serial.println("[STREAM] Started");
}

void handle_cmd() {
  if (server.hasArg("act")) {
    char cmd = server.arg("act").charAt(0);
    if (isValidCommand(cmd)) queueCommand(cmd);
    server.send(200, "text/plain", "OK");
  } else server.send(400, "text/plain", "Invalid");
}

void commandForwardTask(void *param) {
  while (true) {
    char cmd = dequeueCommand();
    if (cmd != 0) {
      bool sent = sendEspNow(cmd);
      Serial.printf("[CMD] %c %s\n", cmd, sent ? "✓" : "✗");
    }
    vTaskDelay(10 / portTICK_PERIOD_MS);
  }
}

// ============= Setup & Loop =============
void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(false);
  delay(1000);
  
  Serial.println("\n=== ESP32-S3-CAM v3.2 ===");
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
  Serial.printf("📡 IP: http://%s:81\n", WiFi.localIP().toString().c_str());
  
  initEspNow();
  
  server.on("/", handle_root);
  server.on("/capture", handle_capture);
  server.on("/stream", handle_stream);
  server.on("/cmd", handle_cmd);
  server.begin();
  wsServer.begin();
  
  xTaskCreatePinnedToCore(commandForwardTask, "CMD", 4096, NULL, 1, NULL, 0);
  Serial.println("✓ System Ready!");
}

void loop() {
  server.handleClient();
  pollWebSocketControl();
  
  if (streamActive) {
    if (!streamClient.connected()) {
      streamActive = false;
      streamClient.stop();
    } else {
      unsigned long now = millis();
      if (now - lastStreamFrame >= 33) {
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
  
  while (Serial.available() > 0) {
    char cmd = Serial.read();
    if (isValidCommand(cmd)) queueCommand(cmd);
  }
  
  static unsigned long lastDist = 0;
  if (millis() - lastDist >= 200) {
    lastDist = millis();
    float d = get_distance();
    if (d > 2.0 && d < 400.0) Serial.printf("DIST:%.1f\n", d);
  }
  vTaskDelay(1);
}
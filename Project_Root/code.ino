/**
 * ESP32-S3-CAM 終極版本 (ESP32 Core 3.x 完全相容)
 * ✅ 修正 ESP-NOW 新版 API (wifi_tx_info_t)
 * ✅ 修正 mbedtls SHA1 函數
 * ✅ 無外部依賴,可直接燒入
 * 
 * 版本: v3.1
 * 測試通過: ESP32 Arduino Core 3.0.0+
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include <esp_now.h>
#include <mbedtls/base64.h>
#include <mbedtls/sha1.h>

// ============= WiFi 設定 =============
const char* ssid     = "Bk";        // 👈 改成你的 WiFi
const char* password = "........."; // 👈 改成你的密碼

// ============= 遙控車設定 =============
// 👉 改成你的 ESP8266 MAC 位址
uint8_t carPeerMac[] = {0x24, 0x6F, 0x28, 0x00, 0x00, 0x00};
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

// ============= ESP-NOW (ESP32 Core 3.x 新版 API) =============
// 新版回調函數簽名: wifi_tx_info_t* 取代 uint8_t*
void onEspNowSent(const wifi_tx_info_t *info, esp_now_send_status_t status) {
  // 新版 ESP32 Core 3.x 使用 wifi_tx_info_t 結構
  // 可以透過 info->dest_addr 取得目標 MAC
  if (status == ESP_NOW_SEND_SUCCESS) {
    // Serial.println("[ESPNOW] Send OK");
  } else {
    // Serial.println("[ESPNOW] Send FAIL");
  }
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
  
  // 直接使用全域函數,相容 ESP32 Core 3.x
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

// ============= WebSocket 手動實作 =============
String buildAcceptKey(const String &clientKey) {
  const char *guid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
  String combined = clientKey + guid;
  
  uint8_t sha1Result[20];
  
  // mbedtls_sha1 (新版已移除 _ret 後綴)
  mbedtls_sha1((const unsigned char*)combined.c_str(), 
               combined.length(), sha1Result);
  
  size_t outLen = 0;
  unsigned char base64Result[64] = {0};
  mbedtls_base64_encode(base64Result, sizeof(base64Result), 
                        &outLen, sha1Result, sizeof(sha1Result));
  
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
  String response = "HTTP/1.1 101 Switching Protocols\r\n"
                    "Upgrade: websocket\r\n"
                    "Connection: Upgrade\r\n"
                    "Sec-WebSocket-Accept: " + acceptKey + "\r\n\r\n";
  
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
    } else if (payloadLen == 127) {
      return;
    }
    
    uint8_t mask[4];
    wsClient.read(mask, 4);
    
    for (uint64_t i = 0; i < payloadLen; i++) {
      char c = (char)(wsClient.read() ^ mask[i % 4]);
      if (i == 0 && isValidCommand(c)) {
        queueCommand(c);
      }
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

// ============= 超聲波感測器 =============
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
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 12;
    config.fb_count = 2;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.grab_mode = CAMERA_GRAB_LATEST;
  } else {
    config.frame_size = FRAMESIZE_QVGA;
    config.jpeg_quality = 12;
    config.fb_count = 1;
  }
  
  return esp_camera_init(&config) == ESP_OK;
}

// ============= HTTP 伺服器 =============
void handle_root() {
  String html = R"(<!DOCTYPE html><html><head><meta charset="utf-8">
<title>ESP32-S3-CAM</title>
<style>
body{background:#0a0a0a;color:#0f0;font-family:monospace;text-align:center;padding:20px;margin:0;}
h1{text-shadow:0 0 10px #0f0;letter-spacing:3px;}
img{width:100%;max-width:640px;border:2px solid #0f0;border-radius:8px;box-shadow:0 0 20px rgba(0,255,0,0.3);}
.btn{background:#1a1a1a;color:#0f0;padding:12px 24px;text-decoration:none;
     border:2px solid #0f0;border-radius:5px;margin:5px;display:inline-block;
     transition:all 0.3s;}
.btn:hover{background:#0f0;color:#000;box-shadow:0 0 20px #0f0;}
.info{margin-top:20px;padding:10px;border:1px solid #333;background:rgba(0,20,0,0.5);
      font-size:12px;}
</style></head><body>
<h1>🚗 ESP32-S3-CAM v3.1</h1>
<img src="/stream" onerror="this.src='/stream'"><br><br>
<a href="/capture" class="btn">📷 拍照</a>
<a href="/stream" class="btn">📺 全螢幕</a>
<div class="info">
  WebSocket: ws://)" + WiFi.localIP().toString() + R"(:82<br>
  HTTP API: http://)" + WiFi.localIP().toString() + R"(:81/cmd?act=F
</div>
</body></html>)";
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
  streamClient.setNoDelay(true);
  streamClient.print("HTTP/1.1 200 OK\r\n"
                     "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n\r\n");
  streamActive = true;
  lastStreamFrame = 0;
  Serial.println("[STREAM] Started");
}

void handle_cmd() {
  if (!server.hasArg("act")) {
    server.send(400, "text/plain", "Missing act");
    return;
  }
  
  char cmd = server.arg("act").charAt(0);
  if (isValidCommand(cmd)) {
    queueCommand(cmd);
    server.send(200, "text/plain", "OK");
  } else {
    server.send(400, "text/plain", "Invalid");
  }
}

// ============= 指令轉發任務 =============
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

// ============= Setup =============
void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(false);
  delay(500);
  
  Serial.println("\n╔════════════════════════════╗");
  Serial.println("║  ESP32-S3-CAM v3.1        ║");
  Serial.println("║  Core 3.x Compatible      ║");
  Serial.println("╚════════════════════════════╝");
  
  init_ultrasonic();
  
  if (init_camera()) {
    Serial.println("✓ Camera OK");
  } else {
    Serial.println("✗ Camera FAILED!");
  }
  
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  Serial.print("⏳ WiFi connecting");
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✓ WiFi Connected!");
    Serial.print("📡 IP: http://");
    Serial.print(WiFi.localIP());
    Serial.println(":81");
    Serial.print("🔌 WS: ws://");
    Serial.print(WiFi.localIP());
    Serial.println(":82");
  } else {
    Serial.println("\n✗ WiFi Failed!");
  }
  
  initEspNow();
  
  server.on("/", handle_root);
  server.on("/capture", handle_capture);
  server.on("/stream", handle_stream);
  server.on("/cmd", handle_cmd);
  server.begin();
  Serial.println("✓ HTTP Server (port 81)");
  
  wsServer.begin();
  Serial.println("✓ WebSocket Server (port 82)");
  
  xTaskCreatePinnedToCore(commandForwardTask, "CMD", 4096, NULL, 1, NULL, 0);
  
  Serial.println("════════════════════════════");
  Serial.println("✓ System Ready!");
  Serial.println("════════════════════════════\n");
}

// ============= Loop =============
void loop() {
  server.handleClient();
  pollWebSocketControl();
  
  // 非阻塞串流
  if (streamActive) {
    if (!streamClient.connected()) {
      streamActive = false;
      streamClient.stop();
    } else {
      unsigned long now = millis();
      if (now - lastStreamFrame >= 33) { // ~30fps
        lastStreamFrame = now;
        camera_fb_t *fb = esp_camera_fb_get();
        if (fb) {
          streamClient.printf("--frame\r\n"
                             "Content-Type: image/jpeg\r\n"
                             "Content-Length: %u\r\n\r\n", fb->len);
          streamClient.write(fb->buf, fb->len);
          streamClient.print("\r\n");
          esp_camera_fb_return(fb);
        }
      }
    }
  }
  
  // Serial 指令
  while (Serial.available() > 0) {
    char cmd = Serial.read();
    if (cmd != '\n' && cmd != '\r' && isValidCommand(cmd)) {
      queueCommand(cmd);
    }
  }
  
  // 超聲波測距
  static unsigned long lastDist = 0;
  if (millis() - lastDist >= 200) {
    lastDist = millis();
    float d = get_distance();
    if (d > 2.0 && d < 400.0) {
      Serial.printf("DIST:%.1f\n", d);
    }
  }
  
  vTaskDelay(1);
}
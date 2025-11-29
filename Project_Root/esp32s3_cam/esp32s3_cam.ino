/**
 * ESP32-S3-CAM N16R8 終極整合版 (非阻塞式轉發)
 * 修正：使用獨立任務處理 HTTP 轉發，避免阻塞主迴圈
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
WiFiServer controlServer(82);
WiFiClient wsClient;
bool wsHandshakeDone = false;
bool isStreaming = false;
bool espNowReady = false;

// 非阻塞串流用
WiFiClient streamClient;
bool streamActive = false;
unsigned long lastStreamFrame = 0;

// ============= [新增] 指令佇列 =============
#define CMD_QUEUE_SIZE 10
char cmdQueue[CMD_QUEUE_SIZE];
volatile int cmdQueueHead = 0;
volatile int cmdQueueTail = 0;

bool isValidCommand(char cmd) {
  return cmd == 'F' || cmd == 'B' || cmd == 'L' || cmd == 'R' || cmd == 'S' ||
         cmd == 'W' || cmd == 'w';
}

// 將指令加入佇列（非阻塞）
void queueCommand(char cmd) {
  int next = (cmdQueueHead + 1) % CMD_QUEUE_SIZE;
  if (next != cmdQueueTail) {
    cmdQueue[cmdQueueHead] = cmd;
    cmdQueueHead = next;
  }
}

// 從佇列取出指令
char dequeueCommand() {
  if (cmdQueueHead == cmdQueueTail) return 0;
  char cmd = cmdQueue[cmdQueueTail];
  cmdQueueTail = (cmdQueueTail + 1) % CMD_QUEUE_SIZE;
  return cmd;
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

// ============= WebSocket 控制通道（無外部函式庫版） =============
String buildAcceptKey(const String &clientKey) {
  const char *guid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
  String combined = clientKey + guid;

  uint8_t sha1Result[20];
  mbedtls_sha1_ret(reinterpret_cast<const unsigned char *>(combined.c_str()), combined.length(), sha1Result);

  size_t outLen = 0;
  unsigned char base64Result[64] = {0};
  mbedtls_base64_encode(base64Result, sizeof(base64Result), &outLen, sha1Result, sizeof(sha1Result));

  return String(reinterpret_cast<char *>(base64Result));
}

bool performWebSocketHandshake(WiFiClient &client) {
  unsigned long start = millis();
  String request = "";

  while (millis() - start < 1000) {
    while (client.available()) {
      char c = client.read();
      request += c;
      if (request.endsWith("\r\n\r\n")) {
        break;
      }
    }

    if (request.endsWith("\r\n\r\n")) {
      break;
    }

    delay(5);
  }

  int keyIndex = request.indexOf("Sec-WebSocket-Key:");
  if (keyIndex < 0) {
    Serial.println("[WS] Handshake failed: no key");
    return false;
  }

  int keyEnd = request.indexOf('\r', keyIndex);
  if (keyEnd < 0) {
    Serial.println("[WS] Handshake failed: malformed key");
    return false;
  }

  String clientKey = request.substring(keyIndex + 19, keyEnd);
  clientKey.trim();

  String acceptKey = buildAcceptKey(clientKey);
  String response =
      "HTTP/1.1 101 Switching Protocols\r\n"
      "Upgrade: websocket\r\n"
      "Connection: Upgrade\r\n"
      "Sec-WebSocket-Accept: " + acceptKey + "\r\n\r\n";

  client.write(reinterpret_cast<const uint8_t *>(response.c_str()), response.length());
  client.flush();

  Serial.println("[WS] Handshake success");
  return true;
}

void handleWebSocketFrames() {
  if (!wsClient || !wsClient.connected()) {
    return;
  }

  while (wsClient.available() >= 2) {
    uint8_t header[2];
    wsClient.read(header, 2);

    bool fin = header[0] & 0x80;
    uint8_t opcode = header[0] & 0x0F;
    bool masked = header[1] & 0x80;
    uint64_t payloadLen = header[1] & 0x7F;

    (void)fin; // 單一幀控制訊息，無需進一步處理分片

    if (payloadLen == 126) {
      if (wsClient.available() < 2) break;
      uint8_t ext[2];
      wsClient.read(ext, 2);
      payloadLen = (ext[0] << 8) | ext[1];
    } else if (payloadLen == 127) {
      // 控制訊息不會這麼長，直接丟棄
      Serial.println("[WS] Payload too large");
      wsClient.stop();
      wsHandshakeDone = false;
      return;
    }

    if (!masked) {
      Serial.println("[WS] Client frames must be masked");
      wsClient.stop();
      wsHandshakeDone = false;
      return;
    }

    size_t totalNeeded = 4 + payloadLen;
    unsigned long waitStart = millis();
    while (wsClient.connected() && wsClient.available() < totalNeeded && millis() - waitStart < 500) {
      delay(5);
    }

    if (wsClient.available() < totalNeeded) {
      Serial.println("[WS] Frame timeout, closing");
      wsClient.stop();
      wsHandshakeDone = false;
      return;
    }

    uint8_t mask[4];
    wsClient.read(mask, 4);

    String payload = "";
    payload.reserve(payloadLen);
    for (uint64_t i = 0; i < payloadLen; i++) {
      int c = wsClient.read();
      if (c < 0) break;
      payload += static_cast<char>(c ^ mask[i % 4]);
    }

    if (opcode == 0x8) { // close
      wsClient.stop();
      wsHandshakeDone = false;
      return;
    } else if (opcode == 0x9) { // ping -> pong
      uint8_t pongHeader[2] = {0x8A, static_cast<uint8_t>(payloadLen)};
      wsClient.write(pongHeader, 2);
      for (uint64_t i = 0; i < payloadLen; i++) {
        wsClient.write(static_cast<uint8_t>(payload[i]));
      }
    } else if (opcode == 0x1 && fin) { // text
      if (payloadLen > 0) {
        char cmd = payload.charAt(0);
        if (isValidCommand(cmd)) {
          queueCommand(cmd);
          Serial.printf("[WS] CMD %c\n", cmd);
        }
      }
    }
  }
}

void pollWebSocketControl() {
  if (!wsClient || !wsClient.connected()) {
    wsClient.stop();
    wsHandshakeDone = false;

    WiFiClient newClient = controlServer.available();
    if (newClient) {
      wsClient = newClient;
      wsClient.setNoDelay(true);
      Serial.println("[WS] Incoming connection");
      wsHandshakeDone = performWebSocketHandshake(wsClient);
      if (!wsHandshakeDone) {
        wsClient.stop();
      }
    }
    return;
  }

  if (wsHandshakeDone) {
    handleWebSocketFrames();
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

  controlServer.begin();
  controlServer.setNoDelay(true);

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
  pollWebSocketControl();

  // 非阻塞串流：在主迴圈中推送影像，避免佔用 server.handleClient()
  if (streamActive) {
    if (!streamClient.connected()) {
      streamActive = false;
      isStreaming = false;
      streamClient.stop();
      Serial.println("[STREAM] 客戶端中斷");
    } else {
      const unsigned long now = millis();
      if (now - lastStreamFrame >= 30) { // ~33fps 上限
        lastStreamFrame = now;
        camera_fb_t *fb = esp_camera_fb_get();
        if (fb) {
          streamClient.print("--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ");
          streamClient.print(fb->len);
          streamClient.print("\r\n\r\n");
          streamClient.write(fb->buf, fb->len);
          streamClient.print("\r\n");
          esp_camera_fb_return(fb);
        }
      }
    }
  }

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
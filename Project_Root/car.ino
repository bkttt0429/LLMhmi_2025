#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <ESP8266mDNS.h>
#include <Servo.h>
#include <espnow.h>
#include <WiFiUdp.h>

// ============= WiFi 設定 =============
const char* ssid     = "Bk";      // 請確認 WiFi 與相機一致
const char* password = ".........";

// ============= 伺服馬達與腳位 =============
Servo leftServo;
Servo rightServo;
const int LEFT_PIN = 5;  // D1
const int RIGHT_PIN = 4; // D2

// ============= 速度設定 =============
// 停止與全速
const int STOP_VAL = 1500; 
const int SPEED_FWD_L = 1700; 
const int SPEED_BCK_L = 1300; 
const int SPEED_FWD_R = 1300; // 右輪反向安裝，數值相反
const int SPEED_BCK_R = 1700;

// 弧線轉彎 (差速) 設定
// 數值越接近 1500 越慢，越遠越快
const int ARC_INNER_FWD_L = 1550;   // 左輪內側慢速 (接近停止但微動)
const int ARC_OUTER_FWD_L = 1700;   // 左輪外側全速

const int ARC_INNER_FWD_R = 1450;   // 右輪內側慢速
const int ARC_OUTER_FWD_R = 1300;   // 右輪外側全速

// ============= 全域變數 =============
ESP8266WebServer server(80);
WiFiUDP udp;
unsigned long lastCmdTime = 0;
const unsigned long TIMEOUT_MS = 2000; // 2秒無指令自動停止
const uint16_t UDP_PORT = 4210;
char lastCmd = '\0';

// ============= 動作函式 =============

void stopCar() {
  leftServo.writeMicroseconds(STOP_VAL);
  rightServo.writeMicroseconds(STOP_VAL);
}

void goForward() {
  leftServo.writeMicroseconds(SPEED_FWD_L);
  rightServo.writeMicroseconds(SPEED_FWD_R);
}

void goBackward() {
  leftServo.writeMicroseconds(SPEED_BCK_L);
  rightServo.writeMicroseconds(SPEED_BCK_R);
}

// 原地旋轉 (坦克式)
void turnLeft() {
  leftServo.writeMicroseconds(SPEED_BCK_L);
  rightServo.writeMicroseconds(SPEED_FWD_R);
}

void turnRight() {
  leftServo.writeMicroseconds(SPEED_FWD_L);
  rightServo.writeMicroseconds(SPEED_BCK_R);
}

// 弧線轉彎 (邊走邊轉)
void arcTurnLeft() {
  // 左轉時：左輪慢(內側)，右輪快(外側)
  leftServo.writeMicroseconds(ARC_INNER_FWD_L);
  rightServo.writeMicroseconds(ARC_OUTER_FWD_R);
}

void arcTurnRight() {
  // 右轉時：左輪快(外側)，右輪慢(內側)
  leftServo.writeMicroseconds(ARC_OUTER_FWD_L);
  rightServo.writeMicroseconds(ARC_INNER_FWD_R);
}

// 處理接收到的指令
void processCommand(char cmd) {
  lastCmdTime = millis();
  
  // 避免重複刷新 Servo (節省 CPU)
  if (cmd == lastCmd) return;
  lastCmd = cmd;
  
  Serial.printf("[CMD] Recv: %c\n", cmd);
  
  switch (cmd) {
    case 'F': goForward(); break;
    case 'B': goBackward(); break;
    case 'L': turnLeft(); break;       // 原地左轉
    case 'R': turnRight(); break;      // 原地右轉
    case 'Q': arcTurnLeft(); break;    // [新功能] 左前弧線
    case 'E': arcTurnRight(); break;   // [新功能] 右前弧線
    case 'S': stopCar(); break;
    default: stopCar(); break;
  }
}

// ESP-NOW 接收回調
void onDataRecv(uint8_t * mac, uint8_t *incomingData, uint8_t len) {
  if (len > 0) {
    processCommand((char)incomingData[0]);
  }
}

void initEspNow() {
  if (esp_now_init() != 0) {
    Serial.println("[ESPNOW] Init failed");
    return;
  }
  esp_now_set_self_role(ESP_NOW_ROLE_COMBO);
  esp_now_register_recv_cb(onDataRecv);
  Serial.println("[ESPNOW] Ready");
}

// ============= Setup & Loop =============
void setup() {
  Serial.begin(115200);
  delay(500);
  
  leftServo.attach(LEFT_PIN);
  rightServo.attach(RIGHT_PIN);
  stopCar(); 

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  
  Serial.print("\nConnecting WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n✓ Connected!");
  Serial.print("IP: "); Serial.println(WiFi.localIP());

  // 啟動 mDNS
  if (MDNS.begin("boebot")) {
    Serial.println("mDNS started");
  }

  // 啟動 UDP 監聽 (接收來自 PC 的指令)
  udp.begin(UDP_PORT);
  Serial.printf("UDP Listening on port %d\n", UDP_PORT);

  initEspNow();
  
  // HTTP 備援控制
  server.on("/", [](){ server.send(200, "text/plain", "Car Ready"); });
  server.on("/cmd", [](){
    if(server.hasArg("act")) {
      char cmd = server.arg("act").charAt(0);
      processCommand(cmd);
      server.send(200, "text/plain", "OK");
    } else server.send(400, "text/plain", "Bad Request");
  });
  server.begin();
}

void loop() {
  // 1. 處理 HTTP
  server.handleClient();
  MDNS.update();
  
  // 2. 處理 UDP (最快)
  int packetSize = udp.parsePacket();
  if (packetSize) {
    char packetBuffer[255];
    int len = udp.read(packetBuffer, 255);
    if (len > 0) {
      packetBuffer[len] = 0;
      processCommand(packetBuffer[0]);
    }
  }

  // 3. 安全機制：超時停車
  if (millis() - lastCmdTime > TIMEOUT_MS) {
    if (lastCmd != 'S') {
      stopCar();
      lastCmd = 'S';
    }
  }
}
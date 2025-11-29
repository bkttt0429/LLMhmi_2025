#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <ESP8266mDNS.h>
#include <Servo.h>
#include <espnow.h>

// ============= WiFi 設定 =============
const char* ssid     = "Bk";      // 請確認 WiFi 與相機一致
const char* password = ".........";

// ============= 伺服馬達與腳位 =============
Servo leftServo;
Servo rightServo;
const int LEFT_PIN = 5;  // D1
const int RIGHT_PIN = 4; // D2

const int STOP_VAL = 1500; 
const int SPEED_FWD_L = 1700; 
const int SPEED_BCK_L = 1300; 
const int SPEED_FWD_R = 1300; // 右輪反向
const int SPEED_BCK_R = 1700;

// ============= 全域變數 =============
ESP8266WebServer server(80);
unsigned long lastCmdTime = 0;
const unsigned long TIMEOUT_MS = 2000; // 2秒無指令自動停止

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

void turnLeft() {
  leftServo.writeMicroseconds(SPEED_BCK_L);
  rightServo.writeMicroseconds(SPEED_FWD_R);
}

void turnRight() {
  leftServo.writeMicroseconds(SPEED_FWD_L);
  rightServo.writeMicroseconds(SPEED_BCK_R);
}

// 處理接收到的指令
void processCommand(char cmd) {
  lastCmdTime = millis();
  Serial.printf("[CMD] Recv: %c\n", cmd);
  
  switch (cmd) {
    case 'F': goForward(); break;
    case 'B': goBackward(); break;
    case 'L': turnLeft(); break;
    case 'R': turnRight(); break;
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
  Serial.print("MAC: "); Serial.println(WiFi.macAddress()); // 顯示 MAC

  if (MDNS.begin("boebot")) {
    Serial.println("mDNS started: http://boebot.local");
  }

  initEspNow();
  
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
  server.handleClient();
  MDNS.update();
  
  if (millis() - lastCmdTime > TIMEOUT_MS) {
    stopCar(); // 安全機制：超時停車
  }
}
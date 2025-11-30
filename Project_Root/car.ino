#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <ESP8266mDNS.h>
#include <Servo.h>
#include <espnow.h>
#include <WiFiUdp.h>

// ============= WiFi 設定 =============
const char* ssid     = "Bk";
const char* password = ".........";

// ============= 伺服馬達與腳位 =============
Servo leftServo;
Servo rightServo;
const int LEFT_PIN = 5;  // D1
const int RIGHT_PIN = 4; // D2

// ============= 速度設定 (平滑插值用) =============
const int STOP_VAL = 1500;
const int SPEED_FWD_L = 1700;
const int SPEED_BCK_L = 1300;
const int SPEED_FWD_R = 1300;
const int SPEED_BCK_R = 1700;

// 弧線轉彎 (前進時)
const int ARC_INNER_FWD_L = 1550;   // 內側慢速
const int ARC_OUTER_FWD_L = 1700;   // 外側全速
const int ARC_INNER_FWD_R = 1450;
const int ARC_OUTER_FWD_R = 1300;

// 弧線轉彎 (後退時) - 新增
const int ARC_INNER_BCK_L = 1450;
const int ARC_OUTER_BCK_L = 1300;
const int ARC_INNER_BCK_R = 1550;
const int ARC_OUTER_BCK_R = 1700;

// ============= 平滑控制變數 =============
int currentLeftSpeed = STOP_VAL;
int currentRightSpeed = STOP_VAL;
int targetLeftSpeed = STOP_VAL;
int targetRightSpeed = STOP_VAL;
const int SMOOTH_STEP = 20;  // 每次調整幅度 (越小越平滑但反應慢)

// ============= 全域變數 =============
ESP8266WebServer server(80);
WiFiUDP udp;
unsigned long lastCmdTime = 0;
const unsigned long TIMEOUT_MS = 2000;
const uint16_t UDP_PORT = 4210;
String lastCmd = "";

// ============= 平滑速度更新 =============
void smoothUpdate() {
  // 平滑插值到目標速度
  if (currentLeftSpeed < targetLeftSpeed) {
    currentLeftSpeed = min(currentLeftSpeed + SMOOTH_STEP, targetLeftSpeed);
  } else if (currentLeftSpeed > targetLeftSpeed) {
    currentLeftSpeed = max(currentLeftSpeed - SMOOTH_STEP, targetLeftSpeed);
  }
  
  if (currentRightSpeed < targetRightSpeed) {
    currentRightSpeed = min(currentRightSpeed + SMOOTH_STEP, targetRightSpeed);
  } else if (currentRightSpeed > targetRightSpeed) {
    currentRightSpeed = max(currentRightSpeed - SMOOTH_STEP, targetRightSpeed);
  }
  
  leftServo.writeMicroseconds(currentLeftSpeed);
  rightServo.writeMicroseconds(currentRightSpeed);
}

// ============= 動作函式 (設定目標速度) =============
void setSpeed(int leftTarget, int rightTarget) {
  targetLeftSpeed = leftTarget;
  targetRightSpeed = rightTarget;
}

void stopCar() {
  setSpeed(STOP_VAL, STOP_VAL);
}

void goForward() {
  setSpeed(SPEED_FWD_L, SPEED_FWD_R);
}

void goBackward() {
  setSpeed(SPEED_BCK_L, SPEED_BCK_R);
}

void turnLeft() {
  setSpeed(SPEED_BCK_L, SPEED_FWD_R);
}

void turnRight() {
  setSpeed(SPEED_FWD_L, SPEED_BCK_R);
}

void arcTurnLeft() {
  setSpeed(ARC_INNER_FWD_L, ARC_OUTER_FWD_R);
}

void arcTurnRight() {
  setSpeed(ARC_OUTER_FWD_L, ARC_INNER_FWD_R);
}

// [新增] 後退弧線轉彎
void arcTurnLeftBack() {
  setSpeed(ARC_INNER_BCK_L, ARC_OUTER_BCK_R);
}

void arcTurnRightBack() {
  setSpeed(ARC_OUTER_BCK_L, ARC_INNER_BCK_R);
}

// 處理接收到的指令
void processCommand(const String& cmd) {
  if (cmd.length() == 0) return;

  lastCmdTime = millis();

  if (cmd == lastCmd) return;
  lastCmd = cmd;

  // 新格式：v{left}:{right}
  if (cmd.charAt(0) == 'v' || cmd.charAt(0) == 'V') {
    int separator = cmd.indexOf(':');
    if (separator > 1) {
      int leftVal = cmd.substring(1, separator).toInt();
      int rightVal = cmd.substring(separator + 1).toInt();

      leftVal = constrain(leftVal, 1000, 2000);
      rightVal = constrain(rightVal, 1000, 2000);

      Serial.printf("[CMD] PWM L:%d R:%d\n", leftVal, rightVal);
      setSpeed(leftVal, rightVal);
      return;
    }
  }

  char c = cmd.charAt(0);
  Serial.printf("[CMD] Recv: %c\n", c);

  switch (c) {
    case 'F': goForward(); break;
    case 'B': goBackward(); break;
    case 'L': turnLeft(); break;
    case 'R': turnRight(); break;
    case 'Q': arcTurnLeft(); break;       // W+A (前進左轉)
    case 'E': arcTurnRight(); break;      // W+D (前進右轉)
    case 'Z': arcTurnLeftBack(); break;   // S+A (後退左轉)
    case 'C': arcTurnRightBack(); break;  // S+D (後退右轉)
    case 'S': stopCar(); break;
    default: stopCar(); break;
  }
}

// ESP-NOW 接收回調
void onDataRecv(uint8_t * mac, uint8_t *incomingData, uint8_t len) {
  if (len > 0) {
    String cmd = String((char*)incomingData).substring(0, len);
    processCommand(cmd);
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

  if (MDNS.begin("boebot")) {
    Serial.println("mDNS started");
  }

  udp.begin(UDP_PORT);
  Serial.printf("UDP Listening on port %d\n", UDP_PORT);

  initEspNow();
  
  server.on("/", [](){ server.send(200, "text/plain", "Car Ready"); });
  server.on("/cmd", [](){
    if(server.hasArg("act")) {
      String cmd = server.arg("act");
      processCommand(cmd);
      server.send(200, "text/plain", "OK");
    } else server.send(400, "text/plain", "Bad Request");
  });
  server.begin();
}

void loop() {
  server.handleClient();
  MDNS.update();
  
  // UDP 處理
  int packetSize = udp.parsePacket();
  if (packetSize) {
    char packetBuffer[255];
    int len = udp.read(packetBuffer, 255);
    if (len > 0) {
      packetBuffer[len] = 0;
      processCommand(String(packetBuffer));
    }
  }

  // 平滑速度更新 (每次 loop 逐步接近目標)
  smoothUpdate();

  // 超時停車
  if (millis() - lastCmdTime > TIMEOUT_MS) {
    if (lastCmd != "S") {
      stopCar();
      lastCmd = "S";
    }
  }
  
  delay(10); // 100Hz 更新率
}

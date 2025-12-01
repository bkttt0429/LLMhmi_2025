#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <ESP8266mDNS.h>
#include <Servo.h>
#include <WiFiUdp.h>

// ============= WiFi 設定 =============
const char* ssid     = "ESP32_Car";
const char* password = "password";

// ============= 伺服馬達與腳位 =============
Servo leftServo;
Servo rightServo;
const int LEFT_PIN = 5;  // D1
const int RIGHT_PIN = 4; // D2

// ============= 超聲波設定 =============
// WARNING: GPIO 0 (D3) is a strapping pin. If pulled LOW at boot, the ESP8266 will not boot into firmware.
// Ensure your ultrasonic sensor does not pull this pin LOW during power-up.
const int US_SIG_PIN = 0; // D3 (GPIO 0)

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

// 弧線轉彎 (後退時)
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
const uint16_t UDP_DIST_PORT = 4211;
const char* CONTROLLER_IP = "192.168.4.1"; // ESP32-S3 IP (Gateway)
String lastCmd = "";

unsigned long lastDistTime = 0;
const unsigned long DIST_INTERVAL_MS = 200;

// ============= 距離量測 =============
float get_distance() {
  pinMode(US_SIG_PIN, OUTPUT);
  digitalWrite(US_SIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(US_SIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(US_SIG_PIN, LOW);
  pinMode(US_SIG_PIN, INPUT_PULLUP);
  unsigned long duration = pulseIn(US_SIG_PIN, HIGH, 30000); // 30ms timeout
  if (duration == 0) return -1.0;
  return duration * 0.034 / 2.0;
}

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

// 後退弧線轉彎
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

      // Serial.printf("[CMD] PWM L:%d R:%d\n", leftVal, rightVal);
      setSpeed(leftVal, rightVal);
      return;
    }
  }

  char c = cmd.charAt(0);
  // Serial.printf("[CMD] Recv: %c\n", c);

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
  
  // Init Ultrasonic
  pinMode(US_SIG_PIN, INPUT_PULLUP);

  server.on("/", [](){ server.send(200, "text/plain", "Car Ready (UDP Mode)"); });
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
  
  // UDP 處理 (Receive Commands)
  int packetSize = udp.parsePacket();
  if (packetSize) {
    char packetBuffer[256]; // Increased buffer size to accommodate null terminator safely
    int len = udp.read(packetBuffer, 255);
    if (len > 0) {
      packetBuffer[len] = 0;
      processCommand(String(packetBuffer));
    }
  }

  // Send Distance Periodically
  if (millis() - lastDistTime >= DIST_INTERVAL_MS) {
    lastDistTime = millis();
    float dist = get_distance();
    if (dist >= 0) {
      udp.beginPacket(CONTROLLER_IP, UDP_DIST_PORT);
      udp.print(dist);
      udp.endPacket();
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

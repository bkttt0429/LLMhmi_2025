#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <ESP8266mDNS.h> // ⭐ 新增：讓你可以用網址連線
#include <Servo.h>


// ============= 參數設定 =============
const char* ssid     = "Bk";      // 請確認您的 WiFi 名稱
const char* password = "........."; // 請確認您的 WiFi 密碼

// 定義伺服馬達物件
Servo leftServo;
Servo rightServo;

// 定義腳位
const int LEFT_PIN = 5;  // D1
const int RIGHT_PIN = 4; // D2

// 定義速度與停止點 (微秒 us)
const int STOP_VAL = 1500; 
const int SPEED_FWD_L = 1700; 
const int SPEED_BCK_L = 1300; 
const int SPEED_FWD_R = 1300; 
const int SPEED_BCK_R = 1700; 

ESP8266WebServer server(80);

// ============= 動作邏輯 =============
void stopCar() {
  leftServo.writeMicroseconds(STOP_VAL);
  rightServo.writeMicroseconds(STOP_VAL);
  Serial.println("STOP");
}

void goForward() {
  leftServo.writeMicroseconds(SPEED_FWD_L);
  rightServo.writeMicroseconds(SPEED_FWD_R);
  Serial.println("FWD");
}

void goBackward() {
  leftServo.writeMicroseconds(SPEED_BCK_L);
  rightServo.writeMicroseconds(SPEED_BCK_R);
  Serial.println("BCK");
}

void turnLeft() {
  leftServo.writeMicroseconds(SPEED_BCK_L);
  rightServo.writeMicroseconds(SPEED_FWD_R);
  Serial.println("LEFT");
}

void turnRight() {
  leftServo.writeMicroseconds(SPEED_FWD_L);
  rightServo.writeMicroseconds(SPEED_BCK_R);
  Serial.println("RIGHT");
}

void processCommand(char cmd) {
  switch (cmd) {
    case 'F': goForward(); break;
    case 'B': goBackward(); break;
    case 'L': turnLeft(); break;
    case 'R': turnRight(); break;
    case 'S': stopCar(); break;
    default: break;
  }
}

// ============= 網頁處理 =============
void handleRoot() {
  String html = "<!DOCTYPE html><html><head><meta charset='utf-8'>";
  html += "<meta name='viewport' content='width=device-width, initial-scale=1, user-scalable=no'>";
  html += "<title>Boe-Bot Control</title>";
  html += "<style>";
  html += "body { font-family: monospace; text-align: center; background-color: #333; color: #0f0; }";
  html += ".btn-group { display: flex; flex-direction: column; align-items: center; gap: 15px; margin-top: 30px; }";
  html += ".row { display: flex; gap: 15px; }";
  html += "button { width: 80px; height: 80px; font-size: 30px; border: 2px solid #0f0; border-radius: 50%; background: #222; color: #0f0; touch-action: manipulation; box-shadow: 0 0 10px #0f0; }";
  html += "button:active { background: #0f0; color: #000; box-shadow: 0 0 20px #0f0; }";
  html += ".stop { border-color: #f00; color: #f00; box-shadow: 0 0 10px #f00; }";
  html += "</style></head><body>";
  
  html += "<h1>ESP Boe-Bot (STA)</h1>";
  html += "<div class='btn-group'>";
  html += "<button onmousedown=\"send('F')\" onmouseup=\"send('S')\" ontouchstart=\"send('F')\" ontouchend=\"send('S')\">^</button>";
  html += "<div class='row'>";
  html += "<button onmousedown=\"send('L')\" onmouseup=\"send('S')\" ontouchstart=\"send('L')\" ontouchend=\"send('S')\">&lt;</button>";
  html += "<button class='stop' onclick=\"send('S')\">O</button>";
  html += "<button onmousedown=\"send('R')\" onmouseup=\"send('S')\" ontouchstart=\"send('R')\" ontouchend=\"send('S')\">&gt;</button>";
  html += "</div>";
  html += "<button onmousedown=\"send('B')\" onmouseup=\"send('S')\" ontouchstart=\"send('B')\" ontouchend=\"send('S')\">v</button>";
  html += "</div>";

  html += "<script>";
  html += "function send(action) { fetch('/cmd?act=' + action).catch(e => console.log(e)); }";
  html += "document.addEventListener('contextmenu', event => event.preventDefault());";
  html += "</script></body></html>";

  server.send(200, "text/html", html);
}

void handleCommand() {
  if (server.hasArg("act")) {
    char cmd = server.arg("act").charAt(0);
    processCommand(cmd);
    uint16_t seq = server.hasArg("seq") ? server.arg("seq").toInt() : 0;
    String ack = "ACK:" + String(seq) + ":" + String(cmd);
    server.send(200, "text/plain", ack);
  } else {
    server.send(400, "text/plain", "Bad Request");
  }
}

void setup() {
  Serial.begin(115200);
  
  leftServo.attach(LEFT_PIN);
  rightServo.attach(RIGHT_PIN);
  stopCar(); 

  // ⭐ 修改為 STA 模式 (連手機熱點)
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  
  Serial.print("\nConnecting to Hotspot");
  // 等待連線
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\n--- Connected! ---");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP()); // 印出手機配給車子的 IP
  Serial.print("IP: ");
  Serial.println(WiFi.localIP()); // 讓 PC Web Server 自動抓取

  // 啟動 mDNS，網址設為 http://boebot.local
  if (MDNS.begin("boebot")) {
    Serial.println("mDNS responder started: http://boebot.local");
  }

  server.on("/", handleRoot);
  server.on("/cmd", handleCommand);
  server.begin();
}

void loop() {
  while (Serial.available() > 0) {
    char incoming = Serial.read();
    if (incoming == '\n' || incoming == '\r') continue;
    processCommand(incoming);
  }
  server.handleClient();
  MDNS.update(); // 處理 mDNS 查詢
}
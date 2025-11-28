#include "camera_config.h"
#include "network.h"
#include "ultrasonic.h"

unsigned long lastDistanceReport = 0;
const unsigned long REPORT_INTERVAL = 500; // 每 500ms 回報一次距離

void setup() {
  Serial.begin(115200);
  
  // 初始化各模組
  init_camera();
  init_wifi();
  init_ultrasonic();
  
  start_web_server();
  
  Serial.println("=== SYSTEM READY ===");
  Serial.println("Ultrasonic sensor initialized on GPIO 21");
}

void loop() {
  server.handleClient();
  
  unsigned long now = millis();
  
  // 定期回報距離數據
  if (now - lastDistanceReport >= REPORT_INTERVAL) {
    lastDistanceReport = now;
    
    float dist = get_distance();
    
    if (dist > 0) {
      // 發送標準格式給 Python 後端
      Serial.printf("DIST:%.1f\n", dist);
      
      // 警告訊息
      if (dist < 10) {
        Serial.printf("WARNING: Obstacle too close! %.1f cm\n", dist);
      } else if (dist < 20) {
        Serial.printf("CAUTION: Object detected at %.1f cm\n", dist);
      }
    } else {
      // 感測器讀取失敗
      Serial.println("DIST:-1.0");
      Serial.println("ERROR: Ultrasonic sensor timeout");
    }
  }
  
  delay(1);
} 
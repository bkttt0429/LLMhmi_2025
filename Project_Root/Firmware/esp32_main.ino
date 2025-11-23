#include "camera_config.h"
#include "network.h"
#include "ultrasonic.h" // 匯入超聲波模組

void setup() {
  Serial.begin(115200);
  
  // 初始化各模組
  init_camera();
  init_wifi();
  init_ultrasonic(); // 初始化超聲波腳位
  
  start_web_server();
}

void loop() {
  server.handleClient();
  
  // 讀取超聲波距離
  float dist = get_distance();
  
  // 如果距離過近，可以做些什麼 (例如閃燈)
  if (dist > 0 && dist < 10) {
    Serial.printf("警告：障礙物過近 %.1f cm\n", dist);
  }
  
  delay(1);
}
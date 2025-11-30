#ifndef ULTRASONIC_H
#define ULTRASONIC_H

#include <Arduino.h>

#define SIG_PIN 21

void init_ultrasonic() {
    pinMode(SIG_PIN, OUTPUT);
    digitalWrite(SIG_PIN, LOW);
}

float get_distance() {
    // 1. 發送觸發脈衝 (維持 OUTPUT 模式)
    digitalWrite(SIG_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(SIG_PIN, LOW);
    
    // 2. 立即切換為 INPUT 模式讀取回聲
    pinMode(SIG_PIN, INPUT);
    
    // 3. 等待高電平開始 (最多等 10ms)
    long timeout = micros() + 10000;
    while (digitalRead(SIG_PIN) == LOW) {
        if (micros() > timeout) return -1.0;
    }
    
    // 4. 測量高電平持續時間
    long startTime = micros();
    timeout = startTime + 30000; // 30ms 超時
    
    while (digitalRead(SIG_PIN) == HIGH) {
        if (micros() > timeout) return -1.0;
    }
    
    long duration = micros() - startTime;
    
    // 5. 恢復為 OUTPUT 模式準備下次觸發
    pinMode(SIG_PIN, OUTPUT);
    digitalWrite(SIG_PIN, LOW);
    
    // 計算距離
    float distance = duration * 0.034 / 2;
    
    if (distance < 2.0 || distance > 400.0) {
        return -1.0;
    }
    
    return distance;
}

#endif

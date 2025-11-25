#ifndef ULTRASONIC_H
#define ULTRASONIC_H

#include <Arduino.h>

// --- 修改這裡 ---
// 改用 GPIO 21，避開 ESP32-S3-CAM 的相機腳位 (IO13 是 PCLK)
#define SIG_PIN 21 

void init_ultrasonic() {
    pinMode(SIG_PIN, INPUT);
}

float get_distance() {
    long duration;
    float distance;

    // 1. 發送 Trigger
    pinMode(SIG_PIN, OUTPUT);
    digitalWrite(SIG_PIN, LOW);
    delayMicroseconds(2);
    digitalWrite(SIG_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(SIG_PIN, LOW);

    // 2. 接收 Echo
    pinMode(SIG_PIN, INPUT);
    duration = pulseIn(SIG_PIN, HIGH, 30000); // 30ms timeout

    if (duration == 0) {
        return -1.0; 
    }

    distance = duration * 0.034 / 2;
    return distance;
}

#endif  
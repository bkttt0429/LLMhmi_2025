#ifndef ULTRASONIC_H
#define ULTRASONIC_H

#define TRIG_PIN 14  // 假設接在 GPIO 14
#define ECHO_PIN 13  // 假設接在 GPIO 13

void init_ultrasonic() {
    pinMode(TRIG_PIN, OUTPUT);
    pinMode(ECHO_PIN, INPUT);
}

float get_distance() {
    digitalWrite(TRIG_PIN, LOW);
    delayMicroseconds(2);
    digitalWrite(TRIG_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(TRIG_PIN, LOW);

    long duration = pulseIn(ECHO_PIN, HIGH, 30000); // 30ms timeout
    if (duration == 0) return -1; // 超時

    return duration * 0.034 / 2;
}

#endif
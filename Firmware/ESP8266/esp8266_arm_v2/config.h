#ifndef CONFIG_H
#define CONFIG_H

#include <Arduino.h>

// === WIFI SETTINGS ===
#define WIFI_SSID "Bk"
#define WIFI_PASS "........."
#define UDP_PORT  4211

// === GEOMETRY (mm) ===
#define GEO_L1 100.0f
#define GEO_L2 100.0f

// === PIN DEFINITIONS (Wemos D1 Mini) ===
// Servo Library uses Standard Arduino Pin Numbers usually, 
// or GPIO numbers. On ESP8266, D1=5, D2=4 etc.
#define PIN_BASE     5  // D1
#define PIN_SHOULDER 4  // D2
#define PIN_ELBOW    0  // D3
#define PIN_GRIPPER  2  // D4

// === SERVO CALIBRATION ===
// Angle = k * q + b
// PWM Range: 500-2500 us

struct ServoConfig {
    int pin;
    int min_us;
    int max_us;
    float k;
    float b;
    float limit_min;
    float limit_max;
};

// Default Configuration
// NOTE: Tune these values based on physical calibration!
const ServoConfig CFG_BASE     = { PIN_BASE,     500, 2500, 1.0, 90.0, -90, 90 };
const ServoConfig CFG_SHOULDER = { PIN_SHOULDER, 500, 2500, 1.0, 90.0, -90, 90 };
const ServoConfig CFG_ELBOW    = { PIN_ELBOW,    500, 2500, 1.0, 90.0, -90, 90 };
const ServoConfig CFG_GRIPPER  = { PIN_GRIPPER,  500, 2500, 1.0, 0.0,   0, 180 };

// === MOTOR SETTINGS ===
#define MAX_SPEED_DEG_PER_SEC 120.0f
#define LOOP_DELAY_MS 20

#endif

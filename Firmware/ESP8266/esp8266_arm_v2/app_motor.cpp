#include "app_motor.h"
#include "config.h"
#include "kinematics.h"
#include <Servo.h>

// === STATE ===
static Servo s_base, s_shoulder, s_elbow, s_gripper;
static bool is_moving = false;

struct AxisState {
    float start;
    float current;
    float target;
    Servo* servo;
    const ServoConfig* cfg;
};

static AxisState axis_base, axis_shoulder, axis_elbow, axis_gripper;

// Profiler State
static unsigned long move_start_time = 0;
static unsigned long move_duration = 0;

// === HELPER ===
// Map logical angle q to Pulse Width (us)
static int q_to_us(float q, const ServoConfig* cfg) {
    // 1. Calibration: theta = k*q + b
    float theta = (q * cfg->k) + cfg->b;
    
    // 2. Limit Clamp
    theta = constrain(theta, cfg->limit_min, cfg->limit_max);
    
    // 3. Map to US
    // Assuming 0-180 mapping logic for standard servo lib
    // map(value, fromLow, fromHigh, toLow, toHigh)
    // We assume the calibrated theta is in "Servo Degrees" (0-180 range approx)
    // Or we map limit_min..limit_max to min_us..max_us? 
    // Usually easier: map 0..180 to min..max.
    
    return map((long)theta, 0, 180, cfg->min_us, cfg->max_us);
}

static float ease_smoothstep(float t) {
    return t * t * (3 - 2 * t);
}

void app_motor_init() {
    // Attach Servos
    s_base.attach(CFG_BASE.pin, CFG_BASE.min_us, CFG_BASE.max_us);
    s_shoulder.attach(CFG_SHOULDER.pin, CFG_SHOULDER.min_us, CFG_SHOULDER.max_us);
    s_elbow.attach(CFG_ELBOW.pin, CFG_ELBOW.min_us, CFG_ELBOW.max_us);
    s_gripper.attach(CFG_GRIPPER.pin, CFG_GRIPPER.min_us, CFG_GRIPPER.max_us);

    // Init State
    axis_base     = { 0, 0, 0, &s_base,     &CFG_BASE };
    axis_shoulder = { 0, 0, 0, &s_shoulder, &CFG_SHOULDER };
    axis_elbow    = { 0, 0, 0, &s_elbow,    &CFG_ELBOW };
    axis_gripper  = { 0, 0, 0, &s_gripper,  &CFG_GRIPPER };

    // Move to Home (0,0,0) logic? 
    // Or just stay at 90 (Safe)
    s_base.write(90); axis_base.current = 0; // Assuming 0->90
    
    Serial.println("[Motor] Initialized");
}

void app_motor_set_target(float x, float y, float z, float gripper_val) {
    // 1. IK Solve
    Angles sol = Kinematics::inverse(x, y, z);
    if (!sol.reachable) {
        Serial.println("[Motor] Unreachable!");
        return;
    }

    // 2. Setup Motion
    axis_base.start = axis_base.current;
    axis_base.target = sol.base;

    axis_shoulder.start = axis_shoulder.current;
    axis_shoulder.target = sol.shoulder;

    axis_elbow.start = axis_elbow.current;
    axis_elbow.target = sol.elbow;

    axis_gripper.start = axis_gripper.current;
    axis_gripper.target = gripper_val;

    // 3. Sync Duration
    float max_dist = 0;
    max_dist = max(max_dist, abs(axis_base.target - axis_base.start));
    max_dist = max(max_dist, abs(axis_shoulder.target - axis_shoulder.start));
    max_dist = max(max_dist, abs(axis_elbow.target - axis_elbow.start));
    
    // Time = Dist / Speed
    // adding min 100ms
    float duration_sec = max_dist / MAX_SPEED_DEG_PER_SEC;
    move_duration = (unsigned long)(duration_sec * 1000);
    if (move_duration < 100) move_duration = 100;

    move_start_time = millis();
    is_moving = true;
}

void app_motor_set_angles(float base, float shoulder, float elbow, float gripper) {
    // Direct Angle Control (Bypass IK)
    
    // 1. Setup Motion
    axis_base.start = axis_base.current;
    axis_base.target = base;

    axis_shoulder.start = axis_shoulder.current;
    axis_shoulder.target = shoulder;

    axis_elbow.start = axis_elbow.current;
    axis_elbow.target = elbow;

    axis_gripper.start = axis_gripper.current;
    axis_gripper.target = gripper;

    // 2. Sync Duration
    float max_dist = 0;
    max_dist = max(max_dist, abs(axis_base.target - axis_base.start));
    max_dist = max(max_dist, abs(axis_shoulder.target - axis_shoulder.start));
    max_dist = max(max_dist, abs(axis_elbow.target - axis_elbow.start));
    
    float duration_sec = max_dist / MAX_SPEED_DEG_PER_SEC;
    move_duration = (unsigned long)(duration_sec * 1000);
    if (move_duration < 100) move_duration = 100;

    move_start_time = millis();
    is_moving = true;
}

void app_motor_update() {
    if (!is_moving) return;

    unsigned long now = millis();
    unsigned long elapsed = now - move_start_time;

    if (elapsed >= move_duration) {
        // Finish
        axis_base.current = axis_base.target;
        axis_shoulder.current = axis_shoulder.target;
        axis_elbow.current = axis_elbow.target;
        axis_gripper.current = axis_gripper.target;
        is_moving = false;
    } else {
        // Interpolate
        float t = (float)elapsed / (float)move_duration;
        float k = ease_smoothstep(t);

        axis_base.current = axis_base.start + (axis_base.target - axis_base.start) * k;
        axis_shoulder.current = axis_shoulder.start + (axis_shoulder.target - axis_shoulder.start) * k;
        axis_elbow.current = axis_elbow.start + (axis_elbow.target - axis_elbow.start) * k;
        axis_gripper.current = axis_gripper.start + (axis_gripper.target - axis_gripper.start) * k;
    }

    // Write Hardware
    s_base.writeMicroseconds(q_to_us(axis_base.current, axis_base.cfg));
    s_shoulder.writeMicroseconds(q_to_us(axis_shoulder.current, axis_shoulder.cfg));
    s_elbow.writeMicroseconds(q_to_us(axis_elbow.current, axis_elbow.cfg));
    s_gripper.writeMicroseconds(q_to_us(axis_gripper.current, axis_gripper.cfg));
}

void app_motor_stop() {
    is_moving = false;
    // Keep current position (Don't detach, just stop updating)
}

bool app_motor_is_moving() {
    return is_moving;
}

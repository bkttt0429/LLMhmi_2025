#include "app_motor.h"
#include "driver/ledc.h"
#include "esp_log.h"
#include "math.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_timer.h"

// --- Hardware Configuration ---
#define MOTOR_LEFT_PIN    21
#define MOTOR_RIGHT_PIN   47

// --- Servo PWM Settings ---
#define PWM_TIMER         LEDC_TIMER_1
#define PWM_MODE          LEDC_LOW_SPEED_MODE
#define PWM_DUTY_RES      LEDC_TIMER_14_BIT // 16384 steps
#define PWM_FREQUENCY     50 

#define LEFT_CHANNEL      LEDC_CHANNEL_2
#define RIGHT_CHANNEL     LEDC_CHANNEL_3

// Mapping Settings
#define INPUT_MIN        -255
#define INPUT_MAX         255

// Output Pulse Widths (microseconds)
#define SERVO_MIN_US      500   // Full Speed CCW
#define SERVO_STOP_US     1500  // Stop
#define SERVO_MAX_US      2500  // Full Speed CW

static const char *TAG = "app_motor";

// Safety State
static int64_t last_cmd_time = 0;
static bool is_running = false;

// Function Prototypes
void motor_safety_task(void *arg);
void app_motor_update_timestamp(void);

// Helper: Convert Microseconds to Duty Cycle value
static uint32_t us_to_duty(int us) {
    if (us < SERVO_MIN_US) us = SERVO_MIN_US;
    if (us > SERVO_MAX_US) us = SERVO_MAX_US;
    return (uint32_t)((us * 16383) / 20000);
}

// Helper: Map range
static long map_range(long x, long in_min, long in_max, long out_min, long out_max) {
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;
}

void app_motor_init(void)
{
    ESP_LOGI(TAG, "Initializing Continuous Servos on GPIO %d, %d", MOTOR_LEFT_PIN, MOTOR_RIGHT_PIN);

    ledc_timer_config_t ledc_timer = {
        .speed_mode       = PWM_MODE,
        .timer_num        = PWM_TIMER,
        .duty_resolution  = PWM_DUTY_RES,
        .freq_hz          = PWM_FREQUENCY,
        .clk_cfg          = LEDC_AUTO_CLK
    };
    ledc_timer_config(&ledc_timer);

    ledc_channel_config_t ledc_channel_left = {
        .speed_mode     = PWM_MODE,
        .channel        = LEFT_CHANNEL,
        .timer_sel      = PWM_TIMER,
        .intr_type      = LEDC_INTR_DISABLE,
        .gpio_num       = MOTOR_LEFT_PIN,
        .duty           = us_to_duty(SERVO_STOP_US),
        .hpoint         = 0
    };
    ledc_channel_config(&ledc_channel_left);

    ledc_channel_config_t ledc_channel_right = {
        .speed_mode     = PWM_MODE,
        .channel        = RIGHT_CHANNEL,
        .timer_sel      = PWM_TIMER,
        .intr_type      = LEDC_INTR_DISABLE,
        .gpio_num       = MOTOR_RIGHT_PIN,
        .duty           = us_to_duty(SERVO_STOP_US),
        .hpoint         = 0
    };
    ledc_channel_config(&ledc_channel_right);

    // [Safety] Start background task to monitor timeout
    xTaskCreate(motor_safety_task, "motor_safety", 2048, NULL, 5, NULL);
}

void app_motor_update_timestamp(void) {
    last_cmd_time = esp_timer_get_time();
    is_running = true;
}

void motor_safety_task(void *arg) {
    while (1) {
        if (is_running) {
            int64_t now = esp_timer_get_time();
            // Timeout: 500ms (500,000 us)
            if (now - last_cmd_time > 500000) {
                ESP_LOGW(TAG, "Motor Safety Timeout! Stopping...");
                app_motor_set_pwm(0, 0); // Stop
                is_running = false;      // Prevent loop spam
            }
        }
        vTaskDelay(pdMS_TO_TICKS(100)); // Check every 100ms
    }
}

void app_motor_set_pwm(int left_val, int right_val)
{
    // Update timestamp on every command (prevent timeout)
    app_motor_update_timestamp();

    // 1. Clamp Input
    if (left_val > INPUT_MAX) left_val = INPUT_MAX;
    if (left_val < INPUT_MIN) left_val = INPUT_MIN;
    if (right_val > INPUT_MAX) right_val = INPUT_MAX;
    if (right_val < INPUT_MIN) right_val = INPUT_MIN;

    // 2. Map Inputs to Pulse Widths
    // [User Specified Restoration]
    // Previous logic had "Swap" (Right->Left, Left->Right) and "Inverted" one side.
    
    // Original:
    // int l_us = map_range(right_val, -255, 255, SERVO_MAX_US, SERVO_MIN_US); // Right val -> Left Pin, Inverted
    // int r_us = map_range(left_val, -255, 255, SERVO_MIN_US, SERVO_MAX_US);  // Left val -> Right Pin, Normal
    
    int l_us = map_range(right_val, INPUT_MIN, INPUT_MAX, SERVO_MAX_US, SERVO_MIN_US);
    int r_us = map_range(left_val, INPUT_MIN, INPUT_MAX, SERVO_MIN_US, SERVO_MAX_US);

    // 3. Apply
    ledc_set_duty(PWM_MODE, LEFT_CHANNEL, us_to_duty(l_us));
    ledc_update_duty(PWM_MODE, LEFT_CHANNEL);

    ledc_set_duty(PWM_MODE, RIGHT_CHANNEL, us_to_duty(r_us));
    ledc_update_duty(PWM_MODE, RIGHT_CHANNEL);
}

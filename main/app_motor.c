#include "app_motor.h"
#include "driver/ledc.h"
#include "esp_log.h"

// Pin Definitions
#define MOTOR_LEFT_PIN    21
#define MOTOR_RIGHT_PIN   47

// PWM Settings
// 50Hz for Servo/ESC compatibility
#define PWM_TIMER         LEDC_TIMER_1
#define PWM_MODE          LEDC_LOW_SPEED_MODE
#define PWM_DUTY_RES       LEDC_TIMER_14_BIT
#define PWM_FREQUENCY     50 // 50Hz (20ms)

#define LEFT_CHANNEL      LEDC_CHANNEL_2
#define RIGHT_CHANNEL     LEDC_CHANNEL_3

// Servo Pulse Widths (microseconds)
// Period = 20000us (50Hz)
// 1000us = 3276 (approx 5% duty)
// 1500us = 4915 (approx 7.5% duty)
// 2000us = 6553 (approx 10% duty)
#define SERVO_MIN_US      1000
#define SERVO_MID_US      1500
#define SERVO_MAX_US      2000

static const char *TAG = "app_motor";

static uint32_t us_to_duty(int us) {
    if (us < SERVO_MIN_US) us = SERVO_MIN_US;
    if (us > SERVO_MAX_US) us = SERVO_MAX_US;
    // Duty = (us / 20000) * 65536
    return (uint32_t)((us * 65536) / 20000);
}

static long map_range(long x, long in_min, long in_max, long out_min, long out_max) {
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;
}

void app_motor_init(void)
{
    ESP_LOGI(TAG, "Initializing Motors on GPIO %d, %d", MOTOR_LEFT_PIN, MOTOR_RIGHT_PIN);

    // Prepare and apply LEDC Timer config
    ledc_timer_config_t ledc_timer = {
        .speed_mode       = PWM_MODE,
        .timer_num        = PWM_TIMER,
        .duty_resolution  = PWM_DUTY_RES,
        .freq_hz          = PWM_FREQUENCY,
        .clk_cfg          = LEDC_AUTO_CLK
    };
    ledc_timer_config(&ledc_timer);

    // Prepare and apply LEDC Channel config
    ledc_channel_config_t ledc_channel_left = {
        .speed_mode     = PWM_MODE,
        .channel        = LEFT_CHANNEL,
        .timer_sel      = PWM_TIMER,
        .intr_type      = LEDC_INTR_DISABLE,
        .gpio_num       = MOTOR_LEFT_PIN,
        .duty           = us_to_duty(SERVO_MID_US),
        .hpoint         = 0
    };
    ledc_channel_config(&ledc_channel_left);

    ledc_channel_config_t ledc_channel_right = {
        .speed_mode     = PWM_MODE,
        .channel        = RIGHT_CHANNEL,
        .timer_sel      = PWM_TIMER,
        .intr_type      = LEDC_INTR_DISABLE,
        .gpio_num       = MOTOR_RIGHT_PIN,
        .duty           = us_to_duty(SERVO_MID_US),
        .hpoint         = 0
    };
    ledc_channel_config(&ledc_channel_right);
}

void app_motor_set_pwm(int left_val, int right_val)
{
    // Input range: -255 to 255
    // Map to 1000..2000
    int l_us = map_range(left_val, -255, 255, SERVO_MIN_US, SERVO_MAX_US);
    int r_us = map_range(right_val, -255, 255, SERVO_MIN_US, SERVO_MAX_US);

    ledc_set_duty(PWM_MODE, LEFT_CHANNEL, us_to_duty(l_us));
    ledc_update_duty(PWM_MODE, LEFT_CHANNEL);

    ledc_set_duty(PWM_MODE, RIGHT_CHANNEL, us_to_duty(r_us));
    ledc_update_duty(PWM_MODE, RIGHT_CHANNEL);

    // ESP_LOGD(TAG, "Motor Set: In(%d, %d) -> Out(%d, %d)us", left_val, right_val, l_us, r_us);
}

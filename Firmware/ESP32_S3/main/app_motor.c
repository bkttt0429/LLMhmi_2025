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
#include "driver/gpio.h"
#include "camera_pins.h" // For LED_PIN

#define PWM_TIMER         LEDC_TIMER_2
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

// Ramping Settings
#define LOOP_DELAY_MS     10    // 100Hz Control Loop

// Acceleration Table: Non-linear Ramping (Ease-In)
// Defines step size per 10ms loop based on current speed bucket (0-255 divided into 8 ranges)
// 0: Start very gentle (2 units/10ms = 200 units/s) -> Approx 1.2s to full speed if linear
// 7: Full response at high speed (40 units/10ms = Instant)
static const int accel_table[8] = { 2, 3, 5, 8, 12, 18, 25, 40 };

static const char *TAG = "app_motor";

// Safety & Control State
static volatile int64_t last_cmd_time = 0;
static volatile bool is_running = false;

// Ramp State (Logical Inputs -255 to 255)
static volatile int target_left = 0;
static volatile int target_right = 0;
static int current_left = 0;
static int current_right = 0;

// Function Prototypes
void motor_control_task(void *arg);
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
    ESP_LOGI(TAG, "Initializing Continuous Servos with RAMPING on GPIO %d, %d", MOTOR_LEFT_PIN, MOTOR_RIGHT_PIN);

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

    // [Control Task] Handles Ramping + Safety
    xTaskCreate(motor_control_task, "motor_ctrl", 4096, NULL, 5, NULL);
}

void app_motor_update_timestamp(void) {
    last_cmd_time = esp_timer_get_time();
    is_running = true;
}

// --- Main Control Loop (Runs on FreeRTOS) ---
void motor_control_task(void *arg) {
    // State for change detection
    int last_applied_l = -999;
    int last_applied_r = -999;
    
    // Debug counter
    int debug_tick = 0;

    while (1) {
        if (is_running) {
            int64_t now = esp_timer_get_time();
            
            // 1. Safety Timeout (500ms)
            if (now - last_cmd_time > 500000) {
                // If timeout, force target to 0 (STOP)
                if (target_left != 0 || target_right != 0) {
                     ESP_LOGW(TAG, "Motor Safety Timeout! Ramping to STOP...");
                     target_left = 0;
                     target_right = 0;
                }
                // Check if we have fully stopped
                if (current_left == 0 && current_right == 0) {
                    is_running = false; 
                }
            }

            // 2. Ramping Logic (Acceleration Table)
            // Determine step size based on current speed
            
            // Left
            int l_idx = abs(current_left) / 32;
            if (l_idx > 7) l_idx = 7;
            int l_step = accel_table[l_idx];

            if (current_left < target_left) {
                current_left += l_step;
                if (current_left > target_left) current_left = target_left;
            } else if (current_left > target_left) {
                current_left -= l_step;
                if (current_left < target_left) current_left = target_left;
            }

            // Right
            int r_idx = abs(current_right) / 32;
            if (r_idx > 7) r_idx = 7;
            int r_step = accel_table[r_idx];

            if (current_right < target_right) {
                current_right += r_step;
                if (current_right > target_right) current_right = target_right;
            } else if (current_right > target_right) {
                current_right -= r_step;
                if (current_right < target_right) current_right = target_right;
            }

            // 3. Map & Apply to Hardware (Only if changed)
            if (current_left != last_applied_l || current_right != last_applied_r) {
                // L_Pin <= Right_Val.  Min->Max
                int l_us = map_range(current_right, INPUT_MIN, INPUT_MAX, SERVO_MIN_US, SERVO_MAX_US);
                
                // R_Pin <= Left_Val.   Max->Min
                int r_us = map_range(current_left, INPUT_MIN, INPUT_MAX, SERVO_MAX_US, SERVO_MIN_US);

                ledc_set_duty(PWM_MODE, LEFT_CHANNEL, us_to_duty(l_us));
                ledc_update_duty(PWM_MODE, LEFT_CHANNEL);

                ledc_set_duty(PWM_MODE, RIGHT_CHANNEL, us_to_duty(r_us));
                ledc_update_duty(PWM_MODE, RIGHT_CHANNEL);
                
                last_applied_l = current_left;
                last_applied_r = current_right;
            }
        }
        
        vTaskDelay(pdMS_TO_TICKS(LOOP_DELAY_MS));
    }
}

// Just updates the TARGET. The Task handles the rest.
void app_motor_set_pwm(int left_val, int right_val)
{
    // Update timestamp
    app_motor_update_timestamp();

    // Clamp
    if (left_val > INPUT_MAX) left_val = INPUT_MAX;
    if (left_val < INPUT_MIN) left_val = INPUT_MIN;
    if (right_val > INPUT_MAX) right_val = INPUT_MAX;
    if (right_val < INPUT_MIN) right_val = INPUT_MIN;

    // Set Target atoms
    // No more double assignment bugs
    target_left = left_val;
    target_right = right_val;
    
    // [DIAGNOSTIC] LED Toggle
    static bool toggle = false;
    toggle = !toggle;
    gpio_set_level(LED_PIN, toggle ? 1 : 0);
}

// [DIAGNOSTIC] Run at startup to prove motors work
// If this runs but WiFi control fails -> Network Issue
// If this fails -> Hardware/Power Issue
void app_motor_run_diagnostic(void) {
    ESP_LOGW(TAG, "--- DIAGNOSTIC START ---");
    ESP_LOGI(TAG, "Testing Forward...");
    // Direct Hardware Access for Test
    ledc_set_duty(PWM_MODE, LEFT_CHANNEL, us_to_duty(SERVO_MAX_US)); // Forward (check polarity)
    ledc_update_duty(PWM_MODE, LEFT_CHANNEL);
    ledc_set_duty(PWM_MODE, RIGHT_CHANNEL, us_to_duty(SERVO_MIN_US)); // Forward (check polarity)
    ledc_update_duty(PWM_MODE, RIGHT_CHANNEL);
    vTaskDelay(pdMS_TO_TICKS(500));

    ESP_LOGI(TAG, "Testing Stop...");
    ledc_set_duty(PWM_MODE, LEFT_CHANNEL, us_to_duty(SERVO_STOP_US));
    ledc_update_duty(PWM_MODE, LEFT_CHANNEL);
    ledc_set_duty(PWM_MODE, RIGHT_CHANNEL, us_to_duty(SERVO_STOP_US));
    ledc_update_duty(PWM_MODE, RIGHT_CHANNEL);
    vTaskDelay(pdMS_TO_TICKS(500));
    
    ESP_LOGI(TAG, "Testing Backward...");
    ledc_set_duty(PWM_MODE, LEFT_CHANNEL, us_to_duty(SERVO_MIN_US)); // Back
    ledc_update_duty(PWM_MODE, LEFT_CHANNEL);
    ledc_set_duty(PWM_MODE, RIGHT_CHANNEL, us_to_duty(SERVO_MAX_US)); // Back
    ledc_update_duty(PWM_MODE, RIGHT_CHANNEL);
    vTaskDelay(pdMS_TO_TICKS(500));

    // Reset to STOP
    ledc_set_duty(PWM_MODE, LEFT_CHANNEL, us_to_duty(SERVO_STOP_US));
    ledc_update_duty(PWM_MODE, LEFT_CHANNEL);
    ledc_set_duty(PWM_MODE, RIGHT_CHANNEL, us_to_duty(SERVO_STOP_US));
    ledc_update_duty(PWM_MODE, RIGHT_CHANNEL);
    
    ESP_LOGI(TAG, "--- DIAGNOSTIC END ---");
}

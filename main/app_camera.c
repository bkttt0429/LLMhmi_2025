#include "app_camera.h"
#include "camera_pins.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "app_camera";

// Retry camera init (Fix for Cold Boot issue)
#define CAMERA_INIT_RETRY_MAX 3
#define CAMERA_POWER_CYCLE_DELAY_MS 100

// Check if camera sensor is healthy
static bool camera_probe(void)
{
    camera_fb_t *fb = esp_camera_fb_get();
    if (fb) {
        esp_camera_fb_return(fb);
        return true;
    }
    return false;
}

esp_err_t app_camera_init(void)
{
    ESP_LOGI(TAG, "Initializing Camera (N16R8 Optimized)...");

    // Check PSRAM
    size_t psram_size = heap_caps_get_total_size(MALLOC_CAP_SPIRAM);
    if (psram_size == 0) {
        ESP_LOGW(TAG, "PSRAM not detected! Falling back to Internal RAM (Low Res).");
    } else {
        ESP_LOGI(TAG, "PSRAM Size: %d MB", psram_size / (1024 * 1024));
    }

    // Camera Config (Optimized for 8MB PSRAM)
    camera_config_t config;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    config.pin_d0 = Y2_GPIO_NUM;
    config.pin_d1 = Y3_GPIO_NUM;
    config.pin_d2 = Y4_GPIO_NUM;
    config.pin_d3 = Y5_GPIO_NUM;
    config.pin_d4 = Y6_GPIO_NUM;
    config.pin_d5 = Y7_GPIO_NUM;
    config.pin_d6 = Y8_GPIO_NUM;
    config.pin_d7 = Y9_GPIO_NUM;
    config.pin_xclk = XCLK_GPIO_NUM;
    config.pin_pclk = PCLK_GPIO_NUM;
    config.pin_vsync = VSYNC_GPIO_NUM;
    config.pin_href = HREF_GPIO_NUM;
    config.pin_sccb_sda = SIOD_GPIO_NUM;
    config.pin_sccb_scl = SIOC_GPIO_NUM;
    config.pin_pwdn = PWDN_GPIO_NUM;
    config.pin_reset = RESET_GPIO_NUM;
    config.xclk_freq_hz = 20000000; // 20MHz

    // Optimization 1: JPEG Format (Hardware Encoding)
    config.pixel_format = PIXFORMAT_JPEG;

    // Optimization 2: Configure Buffers based on RAM availability
    if (psram_size > 0) {
        config.frame_size = FRAMESIZE_SVGA;  // 800x600 (Balanced)
        config.jpeg_quality = 10;            // High Quality (10-12 recommended)
        config.fb_count = 3;                 // Triple Buffering (Reduce drops)
        config.fb_location = CAMERA_FB_IN_PSRAM;
    } else {
        // Fallback for No PSRAM (Internal RAM)
        // Internal RAM is limited (~320KB), so we must use lower res and fewer buffers
        config.frame_size = FRAMESIZE_QVGA;  // 320x240
        config.jpeg_quality = 20;            // Lower quality (higher number) to save space
        config.fb_count = 1;                 // Single Buffer to prevent OOM
        config.fb_location = CAMERA_FB_IN_DRAM;
    }

    config.grab_mode = CAMERA_GRAB_LATEST; // Always grab latest frame

    // Optimization 3: Retry Mechanism
    esp_err_t err = ESP_FAIL;
    for (int retry = 0; retry < CAMERA_INIT_RETRY_MAX; retry++) {
        if (retry > 0) {
            ESP_LOGW(TAG, "Retry %d/%d...", retry, CAMERA_INIT_RETRY_MAX);
            vTaskDelay(pdMS_TO_TICKS(200));
        }

        err = esp_camera_init(&config);

        if (err == ESP_OK) {
            // Verify if camera is truly available
            if (camera_probe()) {
                ESP_LOGI(TAG, "Camera Init Success on attempt %d", retry + 1);
                break;
            } else {
                ESP_LOGW(TAG, "Camera init returned OK but probe failed");
                esp_camera_deinit();
                err = ESP_FAIL;
            }
        } else {
            ESP_LOGE(TAG, "Camera Init Failed: 0x%x", err);
        }
    }

    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Camera Init Failed after %d retries", CAMERA_INIT_RETRY_MAX);
        return err;
    }

    // Optimization 4: Sensor Fine-tuning
    sensor_t *s = esp_camera_sensor_get();
    if (s) {
        // Flip settings (Adjust based on actual mounting)
        s->set_vflip(s, 1);   // Vertical Flip
        s->set_hmirror(s, 0); // Horizontal Mirror

        // Image Quality Tuning
        s->set_brightness(s, 0);     // -2 to 2
        s->set_contrast(s, 0);       // -2 to 2
        s->set_saturation(s, 0);     // -2 to 2
        s->set_sharpness(s, 0);      // -2 to 2
        s->set_denoise(s, 0);        // Denoise (0-8)

        // Auto Exposure / White Balance
        s->set_exposure_ctrl(s, 1);  // Auto Exposure
        s->set_whitebal(s, 1);       // Auto White Balance
        s->set_awb_gain(s, 1);       // AWB Gain
        s->set_wb_mode(s, 0);        // WB Mode (0=auto)

        // Effects and Quality
        s->set_special_effect(s, 0); // No Effect
        s->set_lenc(s, 1);           // Lens Correction
        s->set_gainceiling(s, GAINCEILING_4X); // Gain Ceiling

        ESP_LOGI(TAG, "Sensor settings applied");
    }

    // Memory Check
    ESP_LOGI(TAG, "Free Heap: %d KB, Free PSRAM: %d KB",
             heap_caps_get_free_size(MALLOC_CAP_INTERNAL) / 1024,
             heap_caps_get_free_size(MALLOC_CAP_SPIRAM) / 1024);

    return ESP_OK;
}

// New: Dynamic Resolution Adjustment
esp_err_t app_camera_set_framesize(framesize_t size)
{
    sensor_t *s = esp_camera_sensor_get();
    if (s) {
        if (s->set_framesize(s, size) == 0) {
            ESP_LOGI(TAG, "Framesize changed to %d", size);
            return ESP_OK;
        }
    }
    return ESP_FAIL;
}

// New: Dynamic JPEG Quality Adjustment
esp_err_t app_camera_set_quality(int quality)
{
    sensor_t *s = esp_camera_sensor_get();
    if (s && quality >= 0 && quality <= 63) {
        if (s->set_quality(s, quality) == 0) {
            ESP_LOGI(TAG, "JPEG Quality set to %d", quality);
            return ESP_OK;
        }
    }
    return ESP_FAIL;
}

// New: Health Check (Called periodically)
bool app_camera_health_check(void)
{
    return camera_probe();
}

void app_camera_print_diagnostics(void)
{
    ESP_LOGI(TAG, "=== Camera Diagnostics ===");
    ESP_LOGI(TAG, "Free Heap: %d KB", heap_caps_get_free_size(MALLOC_CAP_INTERNAL) / 1024);
    ESP_LOGI(TAG, "Free PSRAM: %d KB", heap_caps_get_free_size(MALLOC_CAP_SPIRAM) / 1024);
    ESP_LOGI(TAG, "Min Free Heap: %d KB", heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL) / 1024);

    sensor_t *s = esp_camera_sensor_get();
    if (s) {
        ESP_LOGI(TAG, "Camera Status: OK");
    } else {
        ESP_LOGE(TAG, "Camera Status: FAILED");
    }
}
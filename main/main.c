#include <stdio.h>
#include "esp_log.h"
#include "nvs_flash.h"
#include "wifi_sta.h"
#include "app_camera.h"
#include "app_httpd.h"
#include "app_motor.h"
#include "app_udp.h"
#include "camera_pins.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "main";

void app_main(void)
{
    // Initialize NVS
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
      ESP_ERROR_CHECK(nvs_flash_erase());
      ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    // Initialize GPIO for LED (Optional)
    gpio_config_t io_conf = {};
    io_conf.intr_type = GPIO_INTR_DISABLE;
    io_conf.mode = GPIO_MODE_OUTPUT;
    io_conf.pin_bit_mask = (1ULL << LED_PIN);
    io_conf.pull_down_en = 0;
    io_conf.pull_up_en = 0;
    gpio_config(&io_conf);
    gpio_set_level(LED_PIN, 0); // Blink once
    vTaskDelay(100 / portTICK_PERIOD_MS);
    gpio_set_level(LED_PIN, 1); 

    ESP_LOGI(TAG, "Starting ESP32-S3 Car Firmware (Integrated Station Mode)...");

    // 1. Initialize Motors
    app_motor_init();

    // 2. Initialize Camera
    if (app_camera_init() != ESP_OK) {
        ESP_LOGE(TAG, "Camera Init Failed");
        // We continue anyway, maybe motors still work
    }

    // 3. Connect to Wi-Fi (Station Mode)
    wifi_init_sta();

    // 4. Start HTTP Server
    app_httpd_start();

    // 5. Start UDP Listener (for Sensors)
    app_udp_init();

    ESP_LOGI(TAG, "System Ready.");
}

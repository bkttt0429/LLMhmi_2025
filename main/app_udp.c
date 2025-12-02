#include <string.h>
#include <sys/param.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "lwip/err.h"
#include "lwip/sockets.h"
#include "lwip/sys.h"
#include <lwip/netdb.h>

#include "app_udp.h"

static const char *TAG = "app_udp";
static float g_latest_distance = -1.0;
static SemaphoreHandle_t xMutexDistance = NULL;

#define PORT 4211

static void udp_server_task(void *pvParameters)
{
    char rx_buffer[128];
    struct sockaddr_in dest_addr;

    dest_addr.sin_addr.s_addr = htonl(INADDR_ANY);
    dest_addr.sin_family = AF_INET;
    dest_addr.sin_port = htons(PORT);

    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (sock < 0) {
        ESP_LOGE(TAG, "Unable to create socket: errno %d", errno);
        vTaskDelete(NULL);
        return;
    }

    int err = bind(sock, (struct sockaddr *)&dest_addr, sizeof(dest_addr));
    if (err < 0) {
        ESP_LOGE(TAG, "Socket unable to bind: errno %d", errno);
        close(sock);
        vTaskDelete(NULL);
        return;
    }

    ESP_LOGI(TAG, "UDP Server listening on port %d", PORT);

    struct sockaddr_storage source_addr;
    socklen_t socklen = sizeof(source_addr);

    while (1) {
        int len = recvfrom(sock, rx_buffer, sizeof(rx_buffer) - 1, 0, (struct sockaddr *)&source_addr, &socklen);

        if (len < 0) {
            ESP_LOGE(TAG, "recvfrom failed: errno %d", errno);
            break;
        }
        else {
            rx_buffer[len] = 0; // Null-terminate

            // Simple parsing: check for "D:" prefix or just number
            char *p = strstr(rx_buffer, "D:");
            float val = -1.0;
            if (p) {
                val = atof(p + 2);
            } else {
                val = atof(rx_buffer);
            }

            if (val >= 0) {
                if (xMutexDistance != NULL) {
                    if (xSemaphoreTake(xMutexDistance, pdMS_TO_TICKS(10)) == pdTRUE) {
                        g_latest_distance = val;
                        xSemaphoreGive(xMutexDistance);
                    }
                }
            }
        }
    }

    if (sock != -1) {
        shutdown(sock, 0);
        close(sock);
    }
    vTaskDelete(NULL);
}

void app_udp_init(void)
{
    if (xMutexDistance == NULL) {
        xMutexDistance = xSemaphoreCreateMutex();
    }
    xTaskCreate(udp_server_task, "udp_server", 4096, NULL, 5, NULL);
}

float app_udp_get_distance(void)
{
    float d = -1.0;
    if (xMutexDistance != NULL) {
        if (xSemaphoreTake(xMutexDistance, pdMS_TO_TICKS(10)) == pdTRUE) {
            d = g_latest_distance;
            xSemaphoreGive(xMutexDistance);
        }
    }
    return d;
}

#include "app_udp.h"
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "lwip/err.h"
#include "lwip/sockets.h"
#include "lwip/sys.h"
#include <lwip/netdb.h>
#include "esp_log.h"
#include <stdlib.h>

#define UDP_PORT 4211
static const char *TAG = "app_udp";
static float g_distance = 0.0;
static SemaphoreHandle_t s_mutex = NULL;

static void udp_server_task(void *pvParameters)
{
    char rx_buffer[128];
    struct sockaddr_in dest_addr;

    while (1) {
        dest_addr.sin_addr.s_addr = htonl(INADDR_ANY);
        dest_addr.sin_family = AF_INET;
        dest_addr.sin_port = htons(UDP_PORT);

        int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
        if (sock < 0) {
            ESP_LOGE(TAG, "Unable to create socket: errno %d", errno);
            break;
        }
        ESP_LOGI(TAG, "Socket created");

        int err = bind(sock, (struct sockaddr *)&dest_addr, sizeof(dest_addr));
        if (err < 0) {
            ESP_LOGE(TAG, "Socket unable to bind: errno %d", errno);
        } else {
            ESP_LOGI(TAG, "Socket bound, port %d", UDP_PORT);

            struct sockaddr_storage source_addr;
            socklen_t socklen = sizeof(source_addr);

            while (1) {
                int len = recvfrom(sock, rx_buffer, sizeof(rx_buffer) - 1, 0, (struct sockaddr *)&source_addr, &socklen);

                if (len < 0) {
                    ESP_LOGE(TAG, "recvfrom failed: errno %d", errno);
                    break;
                } else {
                    rx_buffer[len] = 0; // Null-terminate
                    // Expecting ASCII float
                    float d = (float)atof(rx_buffer);
                    if (s_mutex) {
                        xSemaphoreTake(s_mutex, portMAX_DELAY);
                        g_distance = d;
                        xSemaphoreGive(s_mutex);
                    }
                    // ESP_LOGI(TAG, "Received distance: %.2f", d);
                }
            }
        }

        if (sock != -1) {
            ESP_LOGE(TAG, "Shutting down socket and restarting...");
            shutdown(sock, 0);
            close(sock);
        }
        vTaskDelay(2000 / portTICK_PERIOD_MS);
    }
    vTaskDelete(NULL);
}

void app_udp_init(void)
{
    s_mutex = xSemaphoreCreateMutex();
    xTaskCreate(udp_server_task, "udp_server", 4096, NULL, 5, NULL);
}

float app_udp_get_distance(void)
{
    float d = 0.0;
    if (s_mutex) {
        xSemaphoreTake(s_mutex, portMAX_DELAY);
        d = g_distance;
        xSemaphoreGive(s_mutex);
    }
    return d;
}

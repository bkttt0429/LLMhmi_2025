#include "app_httpd.h"
#include "esp_http_server.h"
#include "esp_camera.h"
#include "img_converters.h"
#include "esp_log.h"
#include "app_motor.h"
#include "app_udp.h"
#include <stdlib.h>

static const char *TAG = "app_httpd";

#define PART_BOUNDARY "123456789000000000000987654321"
static const char* _STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* _STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* _STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

// Handler for streaming
static esp_err_t stream_handler(httpd_req_t *req)
{
    camera_fb_t *fb = NULL;
    esp_err_t res = ESP_OK;
    size_t _jpg_buf_len;
    uint8_t *_jpg_buf;
    char *part_buf[64];

    res = httpd_resp_set_type(req, _STREAM_CONTENT_TYPE);
    if (res != ESP_OK) {
        return res;
    }

    while (true) {
        fb = esp_camera_fb_get();
        if (!fb) {
            ESP_LOGE(TAG, "Camera capture failed");
            res = ESP_FAIL;
            break;
        }

        if (fb->format != PIXFORMAT_JPEG) {
            // Need conversion if not JPEG (but we init as JPEG)
             bool jpeg_converted = frame2jpg(fb, 80, &_jpg_buf, &_jpg_buf_len);
             esp_camera_fb_return(fb);
             fb = NULL;
             if(!jpeg_converted){
                 ESP_LOGE(TAG, "JPEG compression failed");
                 res = ESP_FAIL;
             }
        } else {
            _jpg_buf_len = fb->len;
            _jpg_buf = fb->buf;
        }

        if (res == ESP_OK) {
            if (httpd_resp_send_chunk(req, _STREAM_BOUNDARY, strlen(_STREAM_BOUNDARY)) != ESP_OK) {
                break;
            }
            size_t hlen = snprintf((char *)part_buf, 64, _STREAM_PART, _jpg_buf_len);
            if (httpd_resp_send_chunk(req, (const char *)part_buf, hlen) != ESP_OK) {
                break;
            }
            if (httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len) != ESP_OK) {
                break;
            }
        }

        if (fb) {
            esp_camera_fb_return(fb);
            fb = NULL;
            _jpg_buf = NULL;
        } else if (_jpg_buf) {
            free(_jpg_buf);
            _jpg_buf = NULL;
        }

        // Simple delay to control FPS (optional)
        vTaskDelay(pdMS_TO_TICKS(40)); // ~25 FPS
    }
    return res;
}

// Handler for control: /control?left=X&right=Y
static esp_err_t control_handler(httpd_req_t *req)
{
    char buf[100];
    int left_val = 0;
    int right_val = 0;

    // Get query string
    if (httpd_req_get_url_query_str(req, buf, sizeof(buf)) == ESP_OK) {
        char param[16];
        if (httpd_query_key_value(buf, "left", param, sizeof(param)) == ESP_OK) {
            left_val = atoi(param);
        }
        if (httpd_query_key_value(buf, "right", param, sizeof(param)) == ESP_OK) {
            right_val = atoi(param);
        }

        app_motor_set_pwm(left_val, right_val);
        httpd_resp_send(req, "OK", HTTPD_RESP_USE_STRLEN);
    } else {
        httpd_resp_send_404(req);
    }
    return ESP_OK;
}

// Handler for distance: /dist
static esp_err_t dist_handler(httpd_req_t *req)
{
    float d = app_udp_get_distance();
    char buf[16];
    snprintf(buf, sizeof(buf), "%.2f", d);
    httpd_resp_send(req, buf, HTTPD_RESP_USE_STRLEN);
    return ESP_OK;
}

// Handler for light (optional): /light?on=1
static esp_err_t light_handler(httpd_req_t *req)
{
    // Not fully implemented with GPIO, just a stub based on user code request
    // User code: pin 48
    char buf[100];
    int state = 0;
    if (httpd_req_get_url_query_str(req, buf, sizeof(buf)) == ESP_OK) {
        char param[16];
        if (httpd_query_key_value(buf, "on", param, sizeof(param)) == ESP_OK) {
            state = atoi(param);
            // gpio_set_level(LED_PIN, state); // Need to init GPIO in main or here
        }
    }
    httpd_resp_send(req, state ? "ON" : "OFF", HTTPD_RESP_USE_STRLEN);
    return ESP_OK;
}

void app_httpd_start(void)
{
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 80;

    httpd_handle_t server = NULL;

    if (httpd_start(&server, &config) == ESP_OK) {
        httpd_uri_t stream_uri = {
            .uri       = "/stream",
            .method    = HTTP_GET,
            .handler   = stream_handler,
            .user_ctx  = NULL
        };
        httpd_register_uri_handler(server, &stream_uri);

        httpd_uri_t control_uri = {
            .uri       = "/control",
            .method    = HTTP_GET,
            .handler   = control_handler,
            .user_ctx  = NULL
        };
        httpd_register_uri_handler(server, &control_uri);

        httpd_uri_t dist_uri = {
            .uri       = "/dist",
            .method    = HTTP_GET,
            .handler   = dist_handler,
            .user_ctx  = NULL
        };
        httpd_register_uri_handler(server, &dist_uri);

        httpd_uri_t light_uri = {
            .uri       = "/light",
            .method    = HTTP_GET,
            .handler   = light_handler,
            .user_ctx  = NULL
        };
        httpd_register_uri_handler(server, &light_uri);

        ESP_LOGI(TAG, "HTTP Server Started on port 80");
    } else {
        ESP_LOGE(TAG, "Failed to start HTTP Server");
    }
}

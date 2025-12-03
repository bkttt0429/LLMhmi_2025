#include "app_httpd.h"
#include "esp_http_server.h"
#include "esp_camera.h"
#include "img_converters.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "app_motor.h"
#include "app_udp.h"
#include "app_camera.h"
#include <stdlib.h>
#include <sys/socket.h>
#include "lwip/sockets.h"

static const char *TAG = "app_httpd";

#define PART_BOUNDARY "123456789000000000000987654321"
static const char* _STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* _STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* _STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

// ⭐ 效能監控結構
typedef struct {
    uint32_t frame_count;
    uint32_t dropped_frames;
    int64_t last_frame_time;
    float current_fps;
} stream_stats_t;

static stream_stats_t g_stats = {0};

// Improved Stream Handler (Optimization Focus 1)
static esp_err_t stream_handler(httpd_req_t *req)
{
    camera_fb_t *fb = NULL;
    esp_err_t res = ESP_OK;
    size_t _jpg_buf_len = 0;
    uint8_t *_jpg_buf = NULL;
    char part_buf[128];  // Increased buffer size

    int64_t frame_start_time = 0;
    const int64_t target_frame_time_us = 40000; // Lower to 25 FPS (more stable)

    // Fix 1: Set correct Content-Type first
    res = httpd_resp_set_type(req, _STREAM_CONTENT_TYPE);
    if (res != ESP_OK) {
        ESP_LOGE(TAG, "Failed to set response type");
        return res;
    }

    // Fix 2: Disable HTTP cache
    httpd_resp_set_hdr(req, "Cache-Control", "no-store, no-cache, must-revalidate, max-age=0");
    httpd_resp_set_hdr(req, "Pragma", "no-cache");
    httpd_resp_set_hdr(req, "Expires", "0");
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

    // Fix 3: TCP Keep-Alive settings
    int sock = httpd_req_to_sockfd(req);
    if (sock >= 0) {
        int keepalive = 1;
        int keepidle = 5;
        int keepinterval = 5;
        int keepcount = 3;
        setsockopt(sock, SOL_SOCKET, SO_KEEPALIVE, &keepalive, sizeof(int));
        setsockopt(sock, IPPROTO_TCP, TCP_KEEPIDLE, &keepidle, sizeof(int));
        setsockopt(sock, IPPROTO_TCP, TCP_KEEPINTVL, &keepinterval, sizeof(int));
        setsockopt(sock, IPPROTO_TCP, TCP_KEEPCNT, &keepcount, sizeof(int));

        // Fix 4: Disable Nagle algorithm (reduce latency)
        int nodelay = 1;
        setsockopt(sock, IPPROTO_TCP, TCP_NODELAY, &nodelay, sizeof(int));
    }

    ESP_LOGI(TAG, "Stream started");

    while (true) {
        frame_start_time = esp_timer_get_time();

        // Get frame
        fb = esp_camera_fb_get();
        if (!fb) {
            ESP_LOGE(TAG, "Camera capture failed");
            g_stats.dropped_frames++;

            if (g_stats.dropped_frames > 10) {
                ESP_LOGW(TAG, "Too many dropped frames, checking health");
                if (!app_camera_health_check()) {
                    ESP_LOGE(TAG, "Camera unhealthy");
                }
                g_stats.dropped_frames = 0;
            }

            // Fix 5: Short delay after failure then retry
            vTaskDelay(pdMS_TO_TICKS(100));
            continue; // Do not break, retry
        }

        // Process JPEG
        if (fb->format != PIXFORMAT_JPEG) {
            bool jpeg_converted = frame2jpg(fb, 80, &_jpg_buf, &_jpg_buf_len);
            esp_camera_fb_return(fb);
            fb = NULL;
            if (!jpeg_converted) {
                ESP_LOGE(TAG, "JPEG compression failed");
                vTaskDelay(pdMS_TO_TICKS(100));
                continue;
            }
        } else {
            _jpg_buf_len = fb->len;
            _jpg_buf = fb->buf;
        }

        // Fix 6: Send in chunks, check success of each step
        if (res == ESP_OK) {
            // Send boundary
            res = httpd_resp_send_chunk(req, _STREAM_BOUNDARY, strlen(_STREAM_BOUNDARY));
            if (res != ESP_OK) {
                ESP_LOGW(TAG, "Failed to send boundary");
                goto cleanup;
            }

            // Send Header
            size_t hlen = snprintf(part_buf, sizeof(part_buf), _STREAM_PART, _jpg_buf_len);
            res = httpd_resp_send_chunk(req, part_buf, hlen);
            if (res != ESP_OK) {
                ESP_LOGW(TAG, "Failed to send header");
                goto cleanup;
            }

            // Send image data
            res = httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len);
            if (res != ESP_OK) {
                ESP_LOGW(TAG, "Failed to send image data");
                goto cleanup;
            }

            g_stats.frame_count++;
        }

cleanup:
        // Free memory
        if (fb) {
            esp_camera_fb_return(fb);
            fb = NULL;
        } else if (_jpg_buf) {
            free(_jpg_buf);
            _jpg_buf = NULL;
        }

        // If send failed, exit loop
        if (res != ESP_OK) {
            break;
        }

        // FPS calculation
        int64_t frame_end_time = esp_timer_get_time();
        int64_t frame_duration = frame_end_time - frame_start_time;

        if (g_stats.last_frame_time > 0) {
            int64_t actual_interval = frame_start_time - g_stats.last_frame_time;
            if (actual_interval > 0) {
                g_stats.current_fps = 1000000.0f / actual_interval;
            }
        }
        g_stats.last_frame_time = frame_start_time;

        // Frame rate control
        if (frame_duration < target_frame_time_us) {
            int64_t delay_us = target_frame_time_us - frame_duration;
            if (delay_us > 1000) {
                vTaskDelay(pdMS_TO_TICKS(delay_us / 1000));
            }
        }

        // Periodically output stats
        if (g_stats.frame_count % 100 == 0) {
            ESP_LOGI(TAG, "FPS: %.1f | Frames: %lu | Dropped: %lu",
                     g_stats.current_fps,
                     (unsigned long)g_stats.frame_count,
                     (unsigned long)g_stats.dropped_frames);
        }
    }

    ESP_LOGI(TAG, "Stream ended. Total: %lu, Dropped: %lu",
             (unsigned long)g_stats.frame_count,
             (unsigned long)g_stats.dropped_frames);

    return res;
}

// ⭐ 控制處理器（保持不變但加入日誌）
static esp_err_t control_handler(httpd_req_t *req)
{
    char buf[100];
    int left_val = 0;
    int right_val = 0;

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

// 距離處理器
static esp_err_t dist_handler(httpd_req_t *req)
{
    float d = app_udp_get_distance();
    char buf[32];
    snprintf(buf, sizeof(buf), "{\"distance\":%.2f}", d);
    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, buf, HTTPD_RESP_USE_STRLEN);
    return ESP_OK;
}

// ⭐ 新增：狀態查詢 API
static esp_err_t status_handler(httpd_req_t *req)
{
    char buf[256];
    snprintf(buf, sizeof(buf),
             "{\"fps\":%.1f,\"frames\":%u,\"dropped\":%u,\"heap\":%u,\"psram\":%u}",
             g_stats.current_fps,
             g_stats.frame_count,
             g_stats.dropped_frames,
             heap_caps_get_free_size(MALLOC_CAP_INTERNAL) / 1024,
             heap_caps_get_free_size(MALLOC_CAP_SPIRAM) / 1024);

    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, buf, HTTPD_RESP_USE_STRLEN);
    return ESP_OK;
}

// ⭐ 新增：設定 API（動態調整解析度/品質）
static esp_err_t settings_handler(httpd_req_t *req)
{
    char buf[100];

    if (httpd_req_get_url_query_str(req, buf, sizeof(buf)) == ESP_OK) {
        char param[16];

        // 調整 JPEG 品質
        if (httpd_query_key_value(buf, "quality", param, sizeof(param)) == ESP_OK) {
            int quality = atoi(param);
            app_camera_set_quality(quality);
        }

        // 調整解析度
        if (httpd_query_key_value(buf, "framesize", param, sizeof(param)) == ESP_OK) {
            int framesize = atoi(param);
            app_camera_set_framesize((framesize_t)framesize);
        }

        httpd_resp_send(req, "OK", HTTPD_RESP_USE_STRLEN);
    } else {
        httpd_resp_send_404(req);
    }
    return ESP_OK;
}

// 燈光處理器（保留）
static esp_err_t light_handler(httpd_req_t *req)
{
    char buf[100];
    int state = 0;
    if (httpd_req_get_url_query_str(req, buf, sizeof(buf)) == ESP_OK) {
        char param[16];
        if (httpd_query_key_value(buf, "on", param, sizeof(param)) == ESP_OK) {
            state = atoi(param);
            // GPIO 控制需在 main.c 實作
        }
    }
    httpd_resp_send(req, state ? "ON" : "OFF", HTTPD_RESP_USE_STRLEN);
    return ESP_OK;
}

void app_httpd_start(void)
{
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 80;
    config.stack_size = 8192;  // 增加堆疊以支援大 JPEG
    config.max_uri_handlers = 8;
    config.lru_purge_enable = true;

    httpd_handle_t server = NULL;

    if (httpd_start(&server, &config) == ESP_OK) {
        // 註冊所有 URI
        httpd_uri_t uris[] = {
            {"/stream", HTTP_GET, stream_handler, NULL},
            {"/control", HTTP_GET, control_handler, NULL},
            {"/dist", HTTP_GET, dist_handler, NULL},
            {"/status", HTTP_GET, status_handler, NULL},
            {"/settings", HTTP_GET, settings_handler, NULL},
            {"/light", HTTP_GET, light_handler, NULL}
        };

        for (int i = 0; i < sizeof(uris) / sizeof(httpd_uri_t); i++) {
            httpd_register_uri_handler(server, &uris[i]);
        }

        ESP_LOGI(TAG, "✅ HTTP Server Started on port 80");
        ESP_LOGI(TAG, "   - /stream   : MJPEG Stream");
        ESP_LOGI(TAG, "   - /control  : Motor Control");
        ESP_LOGI(TAG, "   - /dist     : Distance Sensor");
        ESP_LOGI(TAG, "   - /status   : System Status");
        ESP_LOGI(TAG, "   - /settings : Camera Settings");
    } else {
        ESP_LOGE(TAG, "❌ Failed to start HTTP Server");
    }
}
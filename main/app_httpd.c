#include "app_httpd.h"
#include "esp_http_server.h"
#include "esp_camera.h"
#include "img_converters.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"
#include "app_motor.h"
#include "app_udp.h"
#include "app_camera.h"
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>  // ⭐ 用於 PRIu32 等格式化宏
#include <sys/socket.h>
#include "lwip/sockets.h"

static const char *TAG = "app_httpd";

#define PART_BOUNDARY "123456789000000000000987654321"
static const char* _STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* _STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* _STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

// ⭐ Performance Stats Structure
typedef struct {
    uint32_t frame_count;
    uint32_t dropped_frames;
    int64_t last_frame_time;
    float current_fps;
} stream_stats_t;

static stream_stats_t g_stats = {0};

// ⭐ Stream Handler with Optimizations
static esp_err_t stream_handler(httpd_req_t *req)
{
    camera_fb_t *fb = NULL;
    esp_err_t res = ESP_OK;
    size_t _jpg_buf_len = 0;
    uint8_t *_jpg_buf = NULL;
    char part_buf[64];

    int64_t frame_start_time = 0;
    const int64_t target_frame_time_us = 33333; // Target 30 FPS

    res = httpd_resp_set_type(req, _STREAM_CONTENT_TYPE);
    if (res != ESP_OK) {
        return res;
    }

    // Set TCP Keep-Alive
    int sock = httpd_req_to_sockfd(req);
    int keepalive = 1;
    int keepidle = 5;
    int keepinterval = 5;
    int keepcount = 3;
    setsockopt(sock, SOL_SOCKET, SO_KEEPALIVE, &keepalive, sizeof(int));
    setsockopt(sock, IPPROTO_TCP, TCP_KEEPIDLE, &keepidle, sizeof(int));
    setsockopt(sock, IPPROTO_TCP, TCP_KEEPINTVL, &keepinterval, sizeof(int));
    setsockopt(sock, IPPROTO_TCP, TCP_KEEPCNT, &keepcount, sizeof(int));

    char user_agent[512] = {0}; 
    httpd_req_get_hdr_value_str(req, "User-Agent", user_agent, sizeof(user_agent));
    ESP_LOGI(TAG, "Stream started from %s", user_agent[0] ? user_agent : "Unknown");

    while (true) {
        frame_start_time = esp_timer_get_time();

        // Get Latest Frame
        fb = esp_camera_fb_get();
        if (!fb) {
            ESP_LOGE(TAG, "Camera capture failed");
            g_stats.dropped_frames++;
            res = ESP_FAIL;

            // Health Check
            if (g_stats.dropped_frames > 10) {
                ESP_LOGW(TAG, "Too many dropped frames, checking camera health");
                if (!app_camera_health_check()) {
                    ESP_LOGE(TAG, "Camera unhealthy, need manual restart");
                }
                g_stats.dropped_frames = 0;
            }
            break;
        }

        // Handle JPEG Format
        if (fb->format != PIXFORMAT_JPEG) {
            bool jpeg_converted = frame2jpg(fb, 80, &_jpg_buf, &_jpg_buf_len);
            esp_camera_fb_return(fb);
            fb = NULL;
            if (!jpeg_converted) {
                ESP_LOGE(TAG, "JPEG compression failed");
                res = ESP_FAIL;
                break;
            }
        } else {
            _jpg_buf_len = fb->len;
            _jpg_buf = fb->buf;
        }

        // Non-blocking Send
        if (res == ESP_OK) {
            res = httpd_resp_send_chunk(req, _STREAM_BOUNDARY, strlen(_STREAM_BOUNDARY));
            if (res != ESP_OK) break;

            size_t hlen = snprintf(part_buf, sizeof(part_buf), _STREAM_PART, _jpg_buf_len);
            res = httpd_resp_send_chunk(req, part_buf, hlen);
            if (res != ESP_OK) break;

            res = httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len);
            if (res != ESP_OK) break;

            g_stats.frame_count++;
        }

        // Free Memory
        if (fb) {
            esp_camera_fb_return(fb);
            fb = NULL;
        } else if (_jpg_buf) {
            free(_jpg_buf);
            _jpg_buf = NULL;
        }

        // FPS Calculation
        int64_t frame_end_time = esp_timer_get_time();
        int64_t frame_duration = frame_end_time - frame_start_time;

        if (g_stats.last_frame_time > 0) {
            int64_t actual_interval = frame_start_time - g_stats.last_frame_time;
            if (actual_interval > 0) {
                g_stats.current_fps = 1000000.0f / actual_interval;
            }
        }
        g_stats.last_frame_time = frame_start_time;

        // Rate Control
        if (frame_duration < target_frame_time_us) {
            int64_t delay_us = target_frame_time_us - frame_duration;
            if (delay_us > 1000) {
                vTaskDelay(pdMS_TO_TICKS(delay_us / 1000));
            }
        }

        // Periodically Log Stats (使用 PRIu32 宏)
        if (g_stats.frame_count % 100 == 0) {
            ESP_LOGI(TAG, "FPS: %.1f | Frames: %" PRIu32 " | Dropped: %" PRIu32,
                     g_stats.current_fps, g_stats.frame_count, g_stats.dropped_frames);
        }
    }

    ESP_LOGI(TAG, "Stream ended. Total frames: %" PRIu32 ", Dropped: %" PRIu32,
             g_stats.frame_count, g_stats.dropped_frames);

    return res;
}

// Control Handler
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

// Distance Handler
static esp_err_t dist_handler(httpd_req_t *req)
{
    float d = app_udp_get_distance();
    char buf[32];
    snprintf(buf, sizeof(buf), "{\"distance\":%.2f}", d);
    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, buf, HTTPD_RESP_USE_STRLEN);
    return ESP_OK;
}

// ⭐ Status Query API (使用 PRIu32 宏確保跨平台相容)
static esp_err_t status_handler(httpd_req_t *req)
{
    char buf[256];
    uint32_t heap_free = heap_caps_get_free_size(MALLOC_CAP_INTERNAL) / 1024;
    uint32_t psram_free = heap_caps_get_free_size(MALLOC_CAP_SPIRAM) / 1024;
    
    snprintf(buf, sizeof(buf),
             "{\"fps\":%.1f,\"frames\":%" PRIu32 ",\"dropped\":%" PRIu32 
             ",\"heap\":%" PRIu32 ",\"psram\":%" PRIu32 "}",
             g_stats.current_fps,
             g_stats.frame_count,
             g_stats.dropped_frames,
             heap_free,
             psram_free);

    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, buf, HTTPD_RESP_USE_STRLEN);
    return ESP_OK;
}

// ⭐ Settings API
static esp_err_t settings_handler(httpd_req_t *req)
{
    char buf[100];

    if (httpd_req_get_url_query_str(req, buf, sizeof(buf)) == ESP_OK) {
        char param[16];

        // Adjust JPEG Quality
        if (httpd_query_key_value(buf, "quality", param, sizeof(param)) == ESP_OK) {
            int quality = atoi(param);
            app_camera_set_quality(quality);
            ESP_LOGI(TAG, "Quality set to %d", quality);
        }

        // Adjust Resolution
        if (httpd_query_key_value(buf, "framesize", param, sizeof(param)) == ESP_OK) {
            int framesize = atoi(param);
            app_camera_set_framesize((framesize_t)framesize);
            ESP_LOGI(TAG, "Framesize set to %d", framesize);
        }

        httpd_resp_send(req, "OK", HTTPD_RESP_USE_STRLEN);
    } else {
        httpd_resp_send_404(req);
    }
    return ESP_OK;
}

// Light Handler
static esp_err_t light_handler(httpd_req_t *req)
{
    char buf[100];
    int state = 0;
    if (httpd_req_get_url_query_str(req, buf, sizeof(buf)) == ESP_OK) {
        char param[16];
        if (httpd_query_key_value(buf, "on", param, sizeof(param)) == ESP_OK) {
            state = atoi(param);
            ESP_LOGI(TAG, "Light %s", state ? "ON" : "OFF");
        }
    }
    httpd_resp_send(req, state ? "ON" : "OFF", HTTPD_RESP_USE_STRLEN);
    return ESP_OK;
}

void app_httpd_start(void)
{
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 80;
    config.stack_size = 8192;
    config.max_uri_handlers = 8;
    config.lru_purge_enable = true;

    httpd_handle_t server = NULL;

    if (httpd_start(&server, &config) == ESP_OK) {
        // Register all URIs
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
        ESP_LOGI(TAG, "   - /light    : LED Control");
    } else {
        ESP_LOGE(TAG, "❌ Failed to start HTTP Server");
    }
}
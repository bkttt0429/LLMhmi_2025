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
    char part_buf[128];

    // Set response type BEFORE other operations
    res = httpd_resp_set_type(req, _STREAM_CONTENT_TYPE);
    if (res != ESP_OK) {
        ESP_LOGE(TAG, "Failed to set response type");
        return res;
    }

    // Disable response cache
    httpd_resp_set_hdr(req, "Cache-Control", "no-cache, no-store, must-revalidate");
    httpd_resp_set_hdr(req, "Pragma", "no-cache");
    httpd_resp_set_hdr(req, "Expires", "0");

    // Configure TCP socket options
    int sock = httpd_req_to_sockfd(req);
    if (sock < 0) {
        ESP_LOGE(TAG, "Invalid socket");
        return ESP_FAIL;
    }

    // Increase send buffer to prevent blocking
    int sndbuf_size = 32768; // 32KB
    setsockopt(sock, SOL_SOCKET, SO_SNDBUF, &sndbuf_size, sizeof(sndbuf_size));

    // TCP Keep-Alive settings
    int keepalive = 1;
    int keepidle = 3;
    int keepinterval = 2;
    int keepcount = 3;
    setsockopt(sock, SOL_SOCKET, SO_KEEPALIVE, &keepalive, sizeof(int));
    setsockopt(sock, IPPROTO_TCP, TCP_KEEPIDLE, &keepidle, sizeof(int));
    setsockopt(sock, IPPROTO_TCP, TCP_KEEPINTVL, &keepinterval, sizeof(int));
    setsockopt(sock, IPPROTO_TCP, TCP_KEEPCNT, &keepcount, sizeof(int));

    // Disable Nagle's algorithm for lower latency
    int nodelay = 1;
    setsockopt(sock, IPPROTO_TCP, TCP_NODELAY, &nodelay, sizeof(int));

    ESP_LOGI(TAG, "Stream started (socket=%d)", sock);

    int consecutive_errors = 0;
    const int MAX_CONSECUTIVE_ERRORS = 5;

    // Small valid JPEG (1x1 gray pixel) to keep stream alive
    const uint8_t error_jpg[] = {
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01, 0x01, 0x01, 0x00, 0x48,
        0x00, 0x48, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43, 0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
        0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
        0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
        0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
        0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x14, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xDA, 0x00, 0x08,
        0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0x37, 0xFF, 0xD9
    };
    size_t error_jpg_len = sizeof(error_jpg);

    while (true) {
        // Check if connection is still alive
        int error = 0;
        socklen_t len = sizeof(error);
        if (getsockopt(sock, SOL_SOCKET, SO_ERROR, &error, &len) < 0 || error != 0) {
            ESP_LOGW(TAG, "Socket error detected, closing stream");
            break;
        }

        // Get frame with timeout protection
        fb = esp_camera_fb_get();
        if (!fb) {
            // ESP_LOGW(TAG, "Frame capture failed"); // Reduce log spam
            consecutive_errors++;
            g_stats.dropped_frames++;

            if (consecutive_errors >= MAX_CONSECUTIVE_ERRORS) {
                 // Send Dummy Frame to keep connection alive
                 res = httpd_resp_send_chunk(req, _STREAM_BOUNDARY, strlen(_STREAM_BOUNDARY));
                 if (res == ESP_OK) {
                     size_t hlen = snprintf(part_buf, sizeof(part_buf), _STREAM_PART, error_jpg_len);
                     res = httpd_resp_send_chunk(req, part_buf, hlen);
                 }
                 if (res == ESP_OK) {
                     res = httpd_resp_send_chunk(req, (const char *)error_jpg, error_jpg_len);
                 }

                 if (res != ESP_OK) {
                     ESP_LOGE(TAG, "Failed to send dummy frame, client disconnected");
                     break;
                 }

                 vTaskDelay(pdMS_TO_TICKS(1000)); // Wait 1s
                 continue;
            }

            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }

        consecutive_errors = 0; // Reset on success

        // Convert to JPEG if needed
        if (fb->format != PIXFORMAT_JPEG) {
            bool jpeg_converted = frame2jpg(fb, 80, &_jpg_buf, &_jpg_buf_len);
            esp_camera_fb_return(fb);
            fb = NULL;

            if (!jpeg_converted) {
                ESP_LOGE(TAG, "JPEG conversion failed");
                if (_jpg_buf) {
                    free(_jpg_buf);
                    _jpg_buf = NULL;
                }
                continue;
            }
        } else {
            _jpg_buf_len = fb->len;
            _jpg_buf = fb->buf;
        }

        // Send frame with error checking
        if (res == ESP_OK) {
            res = httpd_resp_send_chunk(req, _STREAM_BOUNDARY, strlen(_STREAM_BOUNDARY));
            if (res != ESP_OK) {
                ESP_LOGW(TAG, "Failed to send boundary (client disconnected?)");
                break;
            }

            size_t hlen = snprintf(part_buf, sizeof(part_buf), _STREAM_PART, _jpg_buf_len);
            res = httpd_resp_send_chunk(req, part_buf, hlen);
            if (res != ESP_OK) {
                ESP_LOGW(TAG, "Failed to send header");
                break;
            }

            res = httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len);
            if (res != ESP_OK) {
                ESP_LOGW(TAG, "Failed to send image data");
                break;
            }

            g_stats.frame_count++;
        }

        // Cleanup
        if (fb) {
            esp_camera_fb_return(fb);
            fb = NULL;
        } else if (_jpg_buf) {
            free(_jpg_buf);
            _jpg_buf = NULL;
        }

        // FPS calculation and stats
        int64_t now = esp_timer_get_time();
        if (g_stats.last_frame_time > 0) {
            int64_t interval = now - g_stats.last_frame_time;
            if (interval > 0) {
                g_stats.current_fps = 1000000.0f / interval;
            }
        }
        g_stats.last_frame_time = now;

        // Log stats periodically
        if (g_stats.frame_count % 100 == 0) {
            ESP_LOGI(TAG, "Stream Stats: FPS=%.1f Frames=%" PRIu32 " Dropped=%" PRIu32,
                     g_stats.current_fps, g_stats.frame_count, g_stats.dropped_frames);
        }

        vTaskDelay(pdMS_TO_TICKS(10));
    }

    if (fb) {
        esp_camera_fb_return(fb);
    }
    if (_jpg_buf) {
        free(_jpg_buf);
    }

    ESP_LOGI(TAG, "Stream ended: Total=%" PRIu32 " Dropped=%" PRIu32,
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
    config.ctrl_port = 32768;
    config.max_open_sockets = 7;
    config.max_uri_handlers = 12;
    config.max_resp_headers = 8;
    config.backlog_conn = 5;
    config.lru_purge_enable = true;
    config.recv_wait_timeout = 10;
    config.send_wait_timeout = 10;
    config.stack_size = 8192;
    config.task_priority = 5;
    config.core_id = 1;

    config.global_user_ctx = NULL;
    config.global_user_ctx_free_fn = NULL;
    config.global_transport_ctx = NULL;
    config.global_transport_ctx_free_fn = NULL;
    config.open_fn = NULL;
    config.close_fn = NULL;
    config.uri_match_fn = NULL;

    httpd_handle_t server = NULL;

    if (httpd_start(&server, &config) == ESP_OK) {
        httpd_uri_t uris[] = {
            {"/stream", HTTP_GET, stream_handler, NULL},
            {"/control", HTTP_GET, control_handler, NULL},
            {"/dist", HTTP_GET, dist_handler, NULL},
            {"/status", HTTP_GET, status_handler, NULL},
            {"/settings", HTTP_GET, settings_handler, NULL},
            {"/light", HTTP_GET, light_handler, NULL}
        };

        for (int i = 0; i < sizeof(uris) / sizeof(httpd_uri_t); i++) {
            if (httpd_register_uri_handler(server, &uris[i]) != ESP_OK) {
                ESP_LOGE(TAG, "Failed to register URI: %s", uris[i].uri);
            }
        }

        ESP_LOGI(TAG, "✅ HTTP Server Started");
        ESP_LOGI(TAG, "   Available endpoints:");
        ESP_LOGI(TAG, "   - GET  /stream   (MJPEG Stream)");
        ESP_LOGI(TAG, "   - GET  /control  (Motor Control)");
        ESP_LOGI(TAG, "   - GET  /dist     (Distance Sensor)");
        ESP_LOGI(TAG, "   - GET  /status   (System Status)");
        ESP_LOGI(TAG, "   - GET  /settings (Camera Settings)");
        ESP_LOGI(TAG, "   - GET  /light    (LED Control)");
    } else {
        ESP_LOGE(TAG, "❌ HTTP Server Start Failed");
    }
}
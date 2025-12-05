#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdlib.h>

// Mock ESP-IDF Types and Macros
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_LOGI(tag, fmt, ...) printf("INFO: " fmt "\n", ##__VA_ARGS__)
#define ESP_LOGE(tag, fmt, ...) printf("ERROR: " fmt "\n", ##__VA_ARGS__)
#define HTTPD_DEFAULT_CONFIG() { .server_port = 80, .ctrl_port = 32768, .max_open_sockets = 7, .backlog_conn = 5, .lru_purge_enable = true, .recv_wait_timeout = 5, .send_wait_timeout = 5, .global_user_ctx = NULL, .global_user_ctx_free_fn = NULL, .transport_mode = HTTPD_TRANSPORT_MODE_TCP, .send_func = NULL, .recv_func = NULL, .open_fn = NULL, .close_fn = NULL, .uri_match_fn = NULL }

typedef int esp_err_t;
typedef void* httpd_handle_t;
typedef struct {
    unsigned task_priority;
    size_t stack_size;
    size_t task_caps; // This is what we are testing!
    uint16_t server_port;
    uint16_t ctrl_port;
    uint16_t max_open_sockets;
    uint16_t backlog_conn;
    bool lru_purge_enable;
    uint16_t recv_wait_timeout;
    uint16_t send_wait_timeout;
    void *global_user_ctx;
    void (*global_user_ctx_free_fn)(void *ctx);
    int transport_mode;
    void* send_func;
    void* recv_func;
    void* open_fn;
    void* close_fn;
    void* uri_match_fn;
} httpd_config_t;

typedef struct {
    const char *uri;
    int method;
    void *handler;
    void *user_ctx;
} httpd_uri_t;

#define HTTP_GET 0
#define HTTPD_RESP_USE_STRLEN -1
#define MALLOC_CAP_SPIRAM (1<<10)
#define MALLOC_CAP_8BIT (1<<2)
#define HTTPD_TRANSPORT_MODE_TCP 1

// Global Mocks
size_t MOCK_PSRAM_SIZE = 0;
httpd_config_t LAST_HTTPD_CONFIG;

// Mock Functions
size_t heap_caps_get_total_size(uint32_t caps) {
    if (caps & MALLOC_CAP_SPIRAM) return MOCK_PSRAM_SIZE;
    return 100000; // Internal RAM
}

esp_err_t httpd_start(httpd_handle_t *handle, const httpd_config_t *config) {
    LAST_HTTPD_CONFIG = *config;
    *handle = (void*)0x1234;
    return ESP_OK;
}

esp_err_t httpd_register_uri_handler(httpd_handle_t handle, const httpd_uri_t *uri_handler) {
    return ESP_OK;
}

// Function to Test (We will include the logic here or stub it)
// Ideally we would verify `app_httpd.c` directly, but it has too many dependencies.
// So we replicate the logic we WANT to implement to verify it compiles and works logically.

void app_httpd_start_logic(void) {
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.max_open_sockets = 7;
    config.lru_purge_enable = true;
    config.stack_size = 8192;
    config.backlog_conn = 5;

    // THE FIX LOGIC
    if (heap_caps_get_total_size(MALLOC_CAP_SPIRAM) > 0) {
        config.task_caps = MALLOC_CAP_SPIRAM;
    } else {
        config.task_caps = MALLOC_CAP_8BIT;
        config.stack_size = 4096; // Reduce stack if internal? Or keep it. Let's say we reduce it slightly or keep it.
        // For safety in verification, let's just test the caps.
    }

    config.server_port = 80;

    httpd_handle_t camera_httpd;
    httpd_start(&camera_httpd, &config);
}

int main() {
    printf("Running Test 1: PSRAM Available\n");
    MOCK_PSRAM_SIZE = 4000000;
    app_httpd_start_logic();
    if (LAST_HTTPD_CONFIG.task_caps == MALLOC_CAP_SPIRAM) {
        printf("PASS: Used SPIRAM when available.\n");
    } else {
        printf("FAIL: Did not use SPIRAM when available.\n");
        return 1;
    }

    printf("Running Test 2: PSRAM Missing\n");
    MOCK_PSRAM_SIZE = 0;
    app_httpd_start_logic();
    if (LAST_HTTPD_CONFIG.task_caps == MALLOC_CAP_8BIT) { // or 0 or whatever we decide
        printf("PASS: Used 8BIT/Internal when SPIRAM missing.\n");
    } else {
        printf("FAIL: Still tried to use SPIRAM or wrong caps when missing. Got: %zu\n", LAST_HTTPD_CONFIG.task_caps);
        return 1;
    }

    return 0;
}

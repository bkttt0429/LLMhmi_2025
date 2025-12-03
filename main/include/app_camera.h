#ifndef APP_CAMERA_H
#define APP_CAMERA_H

#include "esp_err.h"
#include "esp_camera.h"

esp_err_t app_camera_init(void);
esp_err_t app_camera_set_framesize(framesize_t size);
esp_err_t app_camera_set_quality(int quality);
bool app_camera_health_check(void);

#endif

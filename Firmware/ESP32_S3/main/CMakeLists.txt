idf_component_register(SRCS "main.c" "app_camera.c" "app_httpd.c" "app_motor.c" "app_udp.c" "wifi_sta.c"
                    INCLUDE_DIRS "include"
                    PRIV_REQUIRES esp_http_server nvs_flash esp_wifi esp_event driver esp_timer lwip)

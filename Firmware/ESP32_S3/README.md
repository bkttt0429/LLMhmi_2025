# ESP32-S3 CAM 韌體

ESP32-S3 雙核心微控制器韌體，負責：
- 📷 MJPEG 影像串流 (480p @ 20-25 FPS)
- 🚗 差速驅動馬達控制 (HTTP API)
- 📡 UDP 廣播 (自動裝置發現)
- 💾 PSRAM 優化影像緩衝

---

## 🔧 硬體規格

- **MCU**: ESP32-S3 (Dual-Core Xtensa LX7 @ 240MHz)
- **Camera**: OV2640 (2MP)
- **RAM**: 512KB SRAM + 8MB PSRAM
- **Flash**: 16MB
- **Motor Driver**: L298N / TB6612FNG
- **GPIO**: PWM 馬達控制 + 補光燈控制

---

## 🚀 快速開始

### 1. 環境設定
```powershell
# 安裝 ESP-IDF v5.0+
# 參考: https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3/get-started/
```

### 2. 配置 Wi-Fi
編輯 `main/wifi_sta.c`:
```c
#define EXAMPLE_ESP_WIFI_SSID      "你的WiFi名稱"
#define EXAMPLE_ESP_WIFI_PASS      "你的WiFi密碼"
```

### 3. 編譯與燒錄
```powershell
cd Firmware/ESP32_S3
idf.py build
idf.py -p COM3 flash monitor
```

---

## 📡 API 端點

### 1. 馬達控制
```
GET /motor?left={PWM}&right={PWM}
```
參數：
- `left`: 左輪 PWM (-255 ~ 255)
- `right`: 右輪 PWM (-255 ~ 255)

範例：
```bash
curl "http://192.168.4.1/motor?left=200&right=200"
```

### 2. 影像串流
```
GET /stream
```
回傳：MJPEG multipart stream

### 3. 攝影機設定
```
GET /control?var={setting}&val={value}
```

---

## 📁 專案結構

```
ESP32_S3/
├── main/
│   ├── main.c              # 主程式入口
│   ├── app_camera.c        # OV2640 攝影機驅動
│   ├── app_httpd.c         # HTTP 伺服器 (串流 + API)
│   ├── app_motor.c         # PWM 馬達控制
│   ├── app_udp.c           # UDP 廣播
│   ├── wifi_sta.c          # Wi-Fi STA 模式
│   └── include/            # 標頭檔
├── CMakeLists.txt          # ESP-IDF 構建配置
├── sdkconfig               # ESP-IDF 參數設定
├── partitions.csv          # Flash 分區表
└── managed_components/     # ESP Camera 組件
```

---

## ⚡ 效能優化

### PSRAM 配置
- **啟用**: PSRAM OPI (8MB)
- **用途**: 影像緩衝區 + HTTP 緩衝
- **效果**: 支援更高解析度與 FPS

### Wi-Fi 優化
- **模式**: STA (Station)
- **頻寬**: 20MHz
- **省電**: Disabled (最大效能)

---

## 🐛 常見問題

### Q: 攝影機初始化失敗
A: 增加啟動延遲
```c
vTaskDelay(pdMS_TO_TICKS(3000));
```

### Q: 影像串流延遲高
A: 檢查 Wi-Fi 訊號強度，確保 ESP32 與 PC 在同一網段

### Q: 馬達方向錯誤
A: 檢查 `app_motor.c` 的 GPIO 映射

---

## 📊 預設配置

- **Stream Port**: 81
- **UDP Port**: 4213 (廣播)
- **AP SSID**: `ESP32-S3-CAM`
- **預設解析度**: VGA (640x480)
- **JPEG 品質**: 12 (較高)

---

**最後更新**: 2025-12-09  
**ESP-IDF 版本**: v5.0+  
**測試硬體**: ESP32-S3-WROOM-1 + OV2640

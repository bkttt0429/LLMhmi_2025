
# ⚡ ESP32-S3 Firmware Build Guide (Added 2025-12-12)

## 1. Environment Setup (PowerShell)
To compile the firmware, you must first activate the ESP-IDF environment.
Run the following command in PowerShell:

```powershell
. C:\Users\ken\esp\v5.5.1\esp-idf\export.ps1
```

*Note: The leading dot `.` is important! It ensures the environment variables are loaded into the current session.*

## 2. Compilation Steps
 Navigate to the firmware directory and build:

```powershell
# 1. Enter Firmware Directory
cd d:\hmidata\project\Firmware\ESP32_S3

# 2. Set Target (Only needed once per project)
idf.py set-target esp32s3

# 3. Build Firmware
idf.py build
```

## 3. Flash & Monitor
```powershell
# Flash firmware and monitor output (Replace COMx with your device port)
idf.py -p COMx flash monitor
```

## 4. Critical Optimizations (N16R8)
This firmware has been optimized for the ESP32-S3 N16R8 module.
- **WiFi Power Save:** Disabled via `esp_wifi_set_ps(WIFI_PS_NONE)` in `wifi_sta.c` to fix latency.
- **Camera Buffer:** Increased to 5 frames in PSRAM (`app_camera.c`) for smoother video.

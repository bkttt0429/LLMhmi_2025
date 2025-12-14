# Project Development Log (Unified)

**Last Updated:** 2025-12-12 01:10  

---

## 🕒 [2025-12-14 18:00] Motion Control Optimization (Firmware Side)

**Overview:**
Moved the "Slow Start" (Acceleration Ramping) logic from the PC Client (Python) to the Firmware (ESP32) to ensure consistent physics protection (anti-brownout) regardless of network latency.

**Changes:**

1.  **Firmware (`app_motor.c`):**
    *   **Optimized `accel_table`:**
        *   Old: `{ 3, 5, 8, 12, 15, 20, 25, 30 }` (Too aggressive at start)
        *   New: `{ 2, 3, 5, 8, 12, 18, 25, 40 }`
        *   **Effect:** Smoother initial movement (prevents Voltage Sag/Brownout) but fully responsive at high speeds.
    *   **Code Cleanup:** Removed redundant variable assignments in `app_motor_set_pwm`.
    *   **Logic:** The `motor_control_task` now reliably ramps `current_pwm` towards `target_pwm` every 10ms.

2.  **PC Client (`web_server.py`):**
    *   **Reverted `MotionProfiler`:** Removed the Python-side smooth ramping class.
    *   **Direct Control:** `send_control_command` now sends raw target values immediately via WebSocket (or HTTP fallback).
    *   **Benefit:** Eliminates "Double Filtering" latency. The user moves the stick, the command flies to ESP32, and ESP32 handles the smoothing.

**Next Steps:**
- Flash the updated firmware to ESP32.
- Restart `web_server.py`.

## 🕒 [2025-12-12 01:00] Traditional Chinese Version (Latest)

# 項目開發日誌 (Project Development Log)

**日期:** 2025-12-12  
**主題:** ESP32-S3 韌體分析與優化計畫 (針對 N16R8 模組)  
**作者:** Antigravity AI  

---

## 1. 硬件背景與目標
- **目標設備:** ESP32-S3 (N16R8 模組)
- **規格:** 16MB SPI Flash / 8MB Octal PSRAM
- **目標:** 針對高性能影像串流與實時遠端控制 (低延遲) 進行韌體優化。

## 2. 優化分析 (已識別的改進點)

### 🚀 A. 網絡延遲 (關鍵)
- **問題:** `wifi_sta.c` 使用默認的電源/睡眠設定 (`WIFI_PS_MIN_MODEM`)。
- **影響:** 導致隨機的網絡延遲 (100-200ms)，嚴重影響馬達控制的響應速度。
- **解決方案:** 強制關閉 WiFi 省電模式。
  ```c
  esp_wifi_set_ps(WIFI_PS_NONE);
  ```

### 📺 B. 攝像頭性能 (N16R8 專屬)
- **問題:** `app_camera.c` 目前在 PSRAM 中僅分配了 3 個幀緩衝區 (frame buffers)。
- **機會:** N16R8 模組擁有豐富的 PSRAM (8MB)。SVGA MJPEG 幀相對較小 (~100KB)。
- **解決方案:** 增加緩衝區數量以吸收網絡抖動並防止掉幀。
  ```c
  if(heap_caps_get_total_size(MALLOC_CAP_SPIRAM) > 0){
      config.fb_count = 5; // 從 3 增加到 5+
      config.fb_location = CAMERA_FB_IN_PSRAM;
  }
  ```

### 📡 C. 控制協議
- **問題:** 依賴 HTTP (TCP) 進行馬達控制。
- **影響:** 開銷大且會有 "粘滯鍵" 行為 (封包丟失/重傳延遲)。
- **解決方案:** 轉移到 UDP 協議進行控制信號傳輸 (`app_udp.c`)，使用現有的發現端口或專用控制端口。

### ⚡ D. 系統時鐘
- **提議:** 測試將 XCLK 從 20MHz 提高到 24MHz，以潛在提升傳感器幀率上限，但需等待穩定性驗證。

## 3. 風險評估 (潛在故障)

### ⚠️ A. 硬件初始化 ("冷啟動" Bug)
- **觀察:** `main.c` 包含一個硬性的 3 秒延遲 (`vTaskDelay(3000)`) 在攝像頭初始化之前。
- **風險:** 這表明潛在的硬件復位/電源時序問題。固定延遲在不同溫度/電源變化下是不可靠的。
- **緩解:** 實作一個強壯的 "重試循環 (Retry Loop)" 來進行攝像頭初始化，而不是固定等待。

### 🔋 B. 電源穩定性 (Brownout)
- **觀察:** WiFi 發射峰值 >300mA + 馬達啟動突波電流。
- **風險:** 在馬達啟動同時進行影像傳輸時，極易觸發 Brownout Detector (掉電復位)。
- **緩解:**
  - 硬件: 確保足夠的大容量電容。
  - 軟件: 實作 PWM "軟啟動 (Soft Start)" (斜坡控制) 以限制湧浪電流。

### 🔒 C. 安全性與可用性
- **觀察:** WiFi 憑證硬編碼在 `wifi_sta.h` 中。
- **風險:** 更換網絡需要重新燒錄。
- **緩解:** 未來實作 WiFi 配網功能 (SmartConfig 或 SoftAP)。

### 🐕 D. 系統看門狗 (Watchdog)
- **觀察:** 主要控制循環中缺乏顯式的看門狗餵食 (Feeding)。
- **風險:** 應用程式卡死 (如在影像捕捉或網絡阻塞時) 可能導致馬達持續運轉無法停止。

## 4. 實作行動計畫

### 核心修復 (立即執行)
- [x] **[WiFi]** 在 `wifi_sta.c` 中加入 `esp_wifi_set_ps(WIFI_PS_NONE)`。
- [x] **[Camera]** 在 `app_camera.c` 中調整 `fb_count` 為 5 且 `jpeg_quality` 為 12。
- [ ] **[Motor]** 在 `app_motor.c` 中實作基本的軟啟動或最大電流限制。

### 功能擴展 (下一階段)
- [ ] **[Control]** 在 `app_udp.c` 中實作馬達指令的 UDP 封包解析。
- [ ] **[System]** 針對攝像頭的特定 `init_retry` 邏輯。

---

## 🕒 [2025-12-12 00:25] English Version (Original)

# Project Development Log

**Date:** 2025-12-12  
**Subject:** ESP32-S3 Firmware Analysis & Optimization Plan (N16R8)  
**Author:** Antigravity AI  

---

## 1. Hardware Context & Objective
- **Target Device:** ESP32-S3 (N16R8 Module)
- **Specs:** 16MB SPI Flash / 8MB Octal PSRAM
- **Goal:** Optimize firmware for high-performance video streaming and real-time remote control (Low Latency).

## 2. Optimization Analysis (Identified Improvements)

### 🚀 A. Network Latency (Critical)
- **Issue:** `wifi_sta.c` uses default power/sleep settings (`WIFI_PS_MIN_MODEM`).
- **Impact:** Causes random latency spikes (100-200ms) significantly affecting motor control responsiveness.
- **Solution:** Force disable WiFi power save.
  ```c
  esp_wifi_set_ps(WIFI_PS_NONE);
  ```

### 📺 B. Camera Performance (N16R8 Specific)
- **Issue:** `app_camera.c` currently allocates only 3 frame buffers in PSRAM.
- **Opportunity:** The N16R8 module has abundant PSRAM (8MB). SVGA MJPEG frames are relatively small (~100KB).
- **Solution:** Increase buffer count to absorb network jitter and prevent frame drops.
  ```c
  if(heap_caps_get_total_size(MALLOC_CAP_SPIRAM) > 0){
      config.fb_count = 5; // Increase from 3 to 5+
      config.fb_location = CAMERA_FB_IN_PSRAM;
  }
  ```

### 📡 C. Control Protocol
- **Issue:** Reliance on HTTP (TCP) for motor control.
- **Impact:** High overhead and "sticky key" behavior (packet loss/retransmission delays).
- **Solution:** Transition to UDP for control signals (`app_udp.c`), using the existing discovery port or a dedicated control port.

### ⚡ D. System Clock
- **Proposal:** Test increasing XCLK from 20MHz to 24MHz to potentially boost sensor frame rate limits, pending stability verification.

## 3. Risk Assessment (Potential Failures)

### ⚠️ A. Hardware Initialization ("Cold Boot" Bug)
- **Observation:** `main.c` includes a hard 3-second delay (`vTaskDelay(3000)`) before camera init.
- **Risk:** Indicates underlying hardware reset/power timing issues. A fixed delay is unreliable across temperature/power variations.
- **Mitigation:** Implement a robust "Retry Loop" for camera initialization instead of a fixed wait.

### 🔋 B. Power Stability (Brownout)
- **Observation:** WiFi TX peaks >300mA + Motor Surge Current.
- **Risk:** High probability of triggering Brownout Detector (reset) during simultaneous motor start and video transmission.
- **Mitigation:**
  - Hardware: Ensure adequate bulk capacitance.
  - Software: Implement PWM "Soft Start" (Ramping) to limit inrush current.

### 🔒 C. Security & Usability
- **Observation:** WiFi credentials hardcoded in `wifi_sta.h`.
- **Risk:** Requires re-flashing to change networks.
- **Mitigation:** Future implementation of WiFi Provisioning (SmartConfig or SoftAP).

### 🐕 D. System Watchdog
- **Observation:** Lack of explicit Watchdog feeding in main control loops.
- **Risk:** Application hang (e.g., in video capture or network blocking) could leave motors running.

## 4. Implementation Action Plan

### Core Fixes (Immediate)
- [ ] **[WiFi]** Add `esp_wifi_set_ps(WIFI_PS_NONE)` in `wifi_sta.c`.
- [ ] **[Camera]** Tune `fb_count` to 5 and `jpeg_quality` to 12 in `app_camera.c`.
- [ ] **[Motor]** Implement rudimentary Soft Start or Max Current limit in `app_motor.c`.

### Feature Expansion (Next Phase)
- [ ] **[Control]** Implement UDP packet parsing for motor commands in `app_udp.c`.
- [ ] **[System]** specific `init_retry` logic for Camera.

---
*Log generated by Antigravity AI*

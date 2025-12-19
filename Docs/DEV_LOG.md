# 專案開發日誌 (統一版)

**最後更新:** 2025-12-15 22:55

---

## 🕒 [2025-12-15 22:50] 超聲波與震動傳感器整合 (UDP/Subnet Fix)

**總覽:**
完成 HC-SR04 超聲波傳感器與震動開關的整合。解決了 Windows 環境下 UDP 廣播封包丟失的問題，並修復了 PC 端接收與顯示的邏輯。

**變更項目:**

1.  **韌體 (ESP8266 MicroPython):**
    *   **UDP 廣播優化:** 將廣播地址從通用的 `255.255.255.255` 修改為子網專用廣播 (如 `10.28.14.255`)，解決 Windows 網絡過濾問題。
    *   **Boot.py:** 延長 Wi-Fi 連接超時時間 (20次重試)，適應手機熱點。
    *   **Sensors:** 新增驅動 `sensors.py`，使用 GPIO 5 (Sonar) 和 GPIO 4 (Vibration)。

2.  **PC 客戶端 (web_server.py):**
    *   **封包解析:** 重構 `discovery_listener_thread`，優先解析傳感器數據 (`d`, `v`)。
    *   **Debug Log:** 加入即時終端機日誌顯示。
    *   **UI:** 網頁右下角即時顯示 "SONAR/VIB" 數值與震動警告。

3.  **系統設計:** 
    *   參見 `Design/sensor_data_flow.mermaid` 流程圖。

---

## 🕒 [2025-12-15 02:30] MicroPython 回歸與 Mk1 適配

**總覽:**
成功將 ESP8266 韌體回退至 **MicroPython** 版本，以符合使用者偏好並簡化除錯流程。同時整合了 **EEZYbotARM Mk1** 的支援，包含特定的機械耦合補償。

**變更項目:**

1.  **韌體 (ESP8266 MicroPython):**
    *   **架構:** 重新編寫 `main.py`, `robot.py`, `kinematics.py` 軟體堆疊。
    *   **Mk1 適配:** 
        *   更新幾何參數: L1=61mm, L2=80mm。
        *   **耦合補償:** 實作 `q3_servo = q3_geom + (q2_geom - 90)` 邏輯，以修正平行連桿機構的連動效應。
    *   **通訊協議 v2.0:**
        *   支援二進位 UDP 封包 (CMD 0x03 角度控制)。
        *   發現信標 (Discovery Beacon): 每秒廣播 `ESP8266_ARM` 以利自動 IP 搜尋。

2.  **PC 客戶端:**
    *   **AI 優化:** 將預設偵測模型更換為 `yolov13n.pt` (Nano) 以改善延遲。
    *   **介面:** 更新 `index.html`，預設選項改為 Nano 模型。

3.  **文件:**
    *   更新 `task.md` 與 `config.json` 以反映 Mk1 設定。

---

## 🕒 [2025-12-14 18:00] 馬達控制優化 (韌體端)

**總覽:**
將 "緩啟動" (加速度控制) 邏輯從 PC 客戶端 (Python) 移至韌體端 (ESP32)，以確保物理保護機制 (防止電壓驟降) 不受網路延遲影響。

**變更項目:**

1.  **韌體 (`app_motor.c`):**
    *   **優化加速表 (`accel_table`):**
        *   舊版: `{ 3, 5, 8, 12, 15, 20, 25, 30 }` (啟動太過激進)
        *   新版: `{ 2, 3, 5, 8, 12, 18, 25, 40 }`
        *   **效果:** 初始移動更平滑 (防止電壓下沉/掉電)，但在高速時仍保持響應。
    *   **程式碼清理:** 移除了 `app_motor_set_pwm` 中多餘的變數賦值。
    *   **邏輯:** `motor_control_task` 現在每 10ms 可靠地將 `current_pwm` 緩升至 `target_pwm`。

2.  **PC 客戶端 (`web_server.py`):**
    *   **移除 `MotionProfiler`:** 刪除了 Python 端的平滑加速類別。
    *   **直接控制:** `send_control_command` 現在透過 WebSocket (或 HTTP fallback) 立即發送原始目標值。
    *   **優勢:** 消除 "雙重濾波" 造成的延遲。使用者移動搖桿，指令直飛 ESP32，由 ESP32 負責平滑處理。

**後續步驟:**
- 將更新的韌體燒錄至 ESP32。
- 重啟 `web_server.py`。

## 🕒 [2025-12-12 01:00] Traditional Chinese Version (Latest)

# 項目開發日誌 (Project Development Log)

**日期:** 2025-12-15  
**主題:** MicroPython 韌體回歸與 Mk1 機構適配  
**作者:** Antigravity AI  

---

## 🕒 [2025-12-15 02:30] MicroPython 回歸與 Mk1 適配

**總覽:**
成功將 ESP8266 韌體回退至 **MicroPython** 版本，以符合使用者偏好並簡化除錯流程。同時整合了 **EEZYbotARM Mk1** 的支援，包含特定的機械耦合補償。

**變更項目:**

1.  **韌體 (ESP8266 MicroPython):**
    *   **架構:** 重新編寫 `main.py`, `robot.py`, `kinematics.py` 軟體堆疊。
    *   **Mk1 適配:** 
        *   更新幾何參數: L1=61mm, L2=80mm。
        *   **耦合補償:** 實作 `q3_servo = q3_geom + (q2_geom - 90)` 邏輯，以修正平行連桿機構的連動效應。
    *   **通訊協議 v2.0:**
        *   支援二進位 UDP 封包 (CMD 0x03 角度控制)。
        *   發現信標 (Discovery Beacon): 每秒廣播 `ESP8266_ARM` 以利自動 IP 搜尋。

2.  **PC 客戶端:**
    *   **AI 優化:** 將預設偵測模型更換為 `yolov13n.pt` (Nano) 以改善延遲。
    *   **介面:** 更新 `index.html`，預設選項改為 Nano 模型。

3.  **文件:**
    *   更新 `task.md` 與 `config.json` 以反映 Mk1 設定。

---

## 🕒 [2025-12-14 18:00] 馬達控制優化 (韌體端)

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

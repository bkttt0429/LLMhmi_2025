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
*日誌由 Antigravity AI 生成*

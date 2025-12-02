# 雙網卡控制架構整合設計方案 (ESP32-S3 Station Mode + ESP8266 Sensors)

## 0. 目標

本架構旨在整合 **ESP32-S3 (Camera + Motor)** 與 **ESP8266 (Sensors)**，兩者皆連線至同一 Wi-Fi AP (SSID: `Bk`)。
PC 也連線至該 AP (或同一區網)，透過區網 IP 進行控制與影像接收。

### 角色分配
1. **Wi-Fi Router (AP)**
   - **SSID**: `Bk`
   - **Password**: `.........`
   - 負責分配 IP 給所有裝置 (DHCP)。

2. **ESP32-S3-CAM (主控端 / Station)**
   - **模式**: Wi-Fi Station (連線至 `Bk`)
   - **IP**: 由 AP 分配 (建議在 Router 設定 Static DHCP 綁定 MAC，例如 `192.168.x.100`)
   - **功能**:
     - 提供 MJPEG 影像串流 (`/stream`)
     - 接收馬達控制指令 (`/control`)
     - 接收 ESP8266 傳來的感測器數據 (UDP)
     - 透過 HTTP 提供感測器數據 (`/dist`)

3. **ESP8266 (感測端 / Station)**
   - **模式**: Wi-Fi Station (連線至 `Bk`)
   - **功能**:
     - 讀取超聲波或其他感測器
     - 透過 UDP 將數據傳送給 ESP32-S3 (Target IP 需指向 ESP32-S3 的 IP)

4. **PC Client (控制端)**
   - **模式**: 連線至 `Bk` (或同一區網)
   - **功能**:
     - 執行 Flask Server + YOLO 物件偵測
     - 傳送控制指令至 ESP32-S3 IP
     - 顯示即時影像與數據

---

## 1. 系統詳細規格

### 1.1 ESP32-S3-CAM (Firmware: ESP-IDF)
*   **Wi-Fi Mode**: Station
*   **SSID**: `Bk`
*   **Password**: `.........`
*   **HTTP API**:
    *   `GET /stream`: 取得 MJPEG 串流
    *   `GET /control?left=<val>&right=<val>`: 馬達控制 (val: -255 ~ 255)
    *   `GET /dist`: 取得最新超聲波距離 (float)
    *   `GET /light?on=<0|1>`: LED 控制 (可選)
*   **UDP Listener**:
    *   Port: `4211`
    *   功能: 接收 ESP8266 廣播或單播的感測數據 (ASCII string)
*   **硬體接腳 (Pinout)**:
    *   **Motor Left**: GPIO 21
    *   **Motor Right**: GPIO 47
    *   **Camera**: Standard ESP32-S3-CAM Pinout (XCLK=15, PCLK=13, VSYNC=6, HREF=7, D0-D7...)
    *   **LED**: GPIO 48 (或其他定義)

### 1.2 ESP8266 (Firmware: Arduino/PlatformIO)
*   **Wi-Fi**: Connect to SSID `Bk`
*   **Protocol**: UDP
*   **Target IP**: ESP32-S3 的 IP (若無法固定 IP，可嘗試 UDP Broadcast 至 `255.255.255.255`，ESP32 需確認是否接收 Broadcast)
*   **Target Port**: `4211`
*   **Payload**: ASCII String (e.g., "125.5") representing distance in cm.

### 1.3 PC Client
*   **Language**: Python (Flask)
*   **Config**:
    *   需設定 ESP32-S3 的 IP (因為不再是固定的 192.168.4.1，需查看 Router 或 ESP32 Log 確認)。
*   **Logic**:
    *   Video Loop: Fetch `http://<ESP32_IP>/stream`.
    *   Control Loop: Send `http://<ESP32_IP>/control?left=...&right=...`.
    *   Sensor Loop: Fetch `http://<ESP32_IP>/dist`.

---

## 2. 開發與部署流程

1. **ESP32-S3**:
   - 使用 ESP-IDF 建立專案 (main 資料夾位於專案根目錄)。
   - 燒錄至 ESP32-S3。
   - 觀察 Serial Monitor 確認取得的 IP 位址。

2. **ESP8266**:
   - 更新 Wi-Fi Credential 連線至 `Bk`。
   - 更新 UDP Target IP 為 ESP32-S3 的 IP。

3. **PC Client**:
   - 修改 `config.py` 中的 IP 設定，填入 ESP32-S3 的實際 IP。
   - 執行 `python web_server.py`。
   - 開啟瀏覽器操作。

---

## 3. 備註
*   馬達控制採用 PWM (50Hz)，模擬 Servo/ESC 訊號 (1000us-2000us) 映射。
*   影像解析度預設 VGA (FRAMESIZE_VGA)。

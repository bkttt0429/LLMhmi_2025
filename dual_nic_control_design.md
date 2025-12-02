# 雙網卡控制架構整合設計方案 (ESP32-S3 Integrated + ESP8266 Sensors)

## 0. 目標

本架構旨在整合 **ESP32-S3 (Camera + Motor)** 與 **ESP8266 (Sensors)**，並讓 PC 透過專用網卡連線至 ESP32-S3 進行即時影像接收與馬達控制。

### 角色分配
1. **ESP32-S3-CAM (主控端 / AP)**
   - **模式**: Wi-Fi SoftAP (`ESP32_Car`, IP: `192.168.4.1`)
   - **功能**:
     - 提供 MJPEG 影像串流 (`/stream`)
     - 接收馬達控制指令 (`/control`)
     - 接收 ESP8266 傳來的感測器數據 (UDP)
     - 透過 HTTP 提供感測器數據 (`/dist`)

2. **ESP8266 (感測端 / Station)**
   - **模式**: Wi-Fi Station (連線至 `ESP32_Car`)
   - **功能**:
     - 讀取超聲波或其他感測器
     - 透過 UDP 將數據傳送給 ESP32-S3

3. **PC Client (控制端)**
   - **模式**: 雙網卡 (Dual NIC)
   - **連線**:
     - **Wi-Fi 1**: 連線至 `ESP32_Car` (192.168.4.x)，專用於控制與影像。
     - **Wi-Fi 2 / Ethernet**: 連線至 Internet (可選)。
   - **功能**:
     - 執行 Flask Server + YOLO 物件偵測
     - 傳送控制指令至 ESP32-S3
     - 顯示即時影像與數據

---

## 1. 系統詳細規格

### 1.1 ESP32-S3-CAM (Firmware: ESP-IDF)
*   **SSID**: `ESP32_Car`
*   **Password**: `password` (或是使用者自訂)
*   **IP**: `192.168.4.1` (Gateway/Subnet: `255.255.255.0`)
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
*   **Wi-Fi**: Connect to SSID `ESP32_Car`
*   **Protocol**: UDP
*   **Target IP**: `192.168.4.1` (or Broadcast `192.168.4.255`)
*   **Target Port**: `4211`
*   **Payload**: ASCII String (e.g., "125.5") representing distance in cm.

### 1.3 PC Client
*   **Language**: Python (Flask)
*   **Logic**:
    *   Startup: Detect Network Interfaces.
    *   Bind Camera/Control traffic to the interface with IP `192.168.4.x`.
    *   Video Loop: Fetch `http://192.168.4.1/stream`.
    *   Control Loop: Send `http://192.168.4.1/control?left=...&right=...`.
    *   Sensor Loop: Fetch `http://192.168.4.1/dist` (Optionally receive UDP directly if forwarded, but fetching from ESP32 is simpler for synchronization). *Note: The previous design had PC listening on UDP 4211. In this new design, ESP32 receives UDP. We can either have ESP32 forward it or store it. Storing and serving via HTTP is robust.*

---

## 2. 開發與部署流程

1. **ESP32-S3**:
   - 使用 ESP-IDF 建立專案。
   - 設定 Partition Table (Large App for Camera)。
   - 燒錄至 ESP32-S3。

2. **ESP8266**:
   - 維持既有程式或更新 Wi-Fi Credential 連線至 `ESP32_Car`。

3. **PC Client**:
   - 執行 `python web_server.py`。
   - 確認網卡自動綁定正確。
   - 開啟瀏覽器 `http://localhost:5000` 操作。

---

## 3. 備註
*   馬達控制採用 PWM (50Hz)，模擬 Servo/ESC 訊號 (1000us-2000us) 或直接 Duty Cycle，視驅動板而定。本案採用 1000us-2000us Mapping。
*   影像解析度預設 QVGA 或 VGA 以確保傳輸流暢度。

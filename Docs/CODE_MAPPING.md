# ESP8266 Firmware Code Mapping (MicroPython)

本文件對照 `Design/firmware_impl.drawio` (ESP12F Flowchart) 中的區塊編號與實際程式碼。

---

## 節點 (29)：Boot & Init WiFi
**檔案位置：** `Firmware/ESP8266/MicroPython/boot.py`
**程式碼行號：** 第 10 – 53 行
**說明：**
開機初始化的第一步。負責連接 Wi-Fi AP，包含 20 次重試邏輯。

## 節點 (30)：Init GPIO (PWM) / Init UDP
**檔案位置：** `Firmware/ESP8266/MicroPython/main.py`
**程式碼行號：** 第 10 – 71 行
**說明：**
系統全域初始化。
*   設定 GPIO (LED, Sensors)。
*   初始化 UDP Socket (Port 4211) 與 UART。

## 節點 (31)：Start WebService (Async Entry)
**檔案位置：** `Firmware/ESP8266/MicroPython/main.py`
**程式碼行號：** 第 135 – 147 行
**說明：**
`main()` 函數進入點。啟動 AsyncIO 事件迴圈 (Event Loop) 並建立所有非同步任務 (Tasks)。

## 節點 (32)：Loop (Async Scheduler)
**檔案位置：** `Firmware/ESP8266/MicroPython/main.py`
**程式碼行號：** 第 148 – 149 行
**說明：**
AsyncIO 的主調度迴圈。負責分時切換執行「傳感器讀取」與「網路監聽」任務。

---

### 分支 A：Client Request (Command Control)

## 節點 (33)：Handle Request (Network Listener)
**檔案位置：** `Firmware/ESP8266/MicroPython/main.py`
**程式碼行號：** 第 57 – 88 行
**說明：**
監聽 UDP 與 Serial 的控制數據。解析 RM 協議封包 (Header, CMD, CRC) 以決定動作。

## 節點 (34)：Write PWM (Robot Action)
**檔案位置：** `Firmware/ESP8266/MicroPython/main.py`
**程式碼行號：** 第 113 – 129 行
**說明：**
根據解析出的指令 (CMD 0x03/0x01) 驅動伺服馬達 (PWM)。*(目前程式碼中 Robot 預設為 Disabled)*

---

### 分支 B：Periodic Sensor Task (Every 100ms)

## 節點 (35)：Read Sonar (PulseIn)
**檔案位置：** `Firmware/ESP8266/MicroPython/sensors.py`
**程式碼行號：** 第 4 – 67 行
**說明：**
觸發 HC-SR04 超聲波 (Trigger/Echo) 並讀取震動開關狀態。

## 節點 (36)：UDP Broadcast
**檔案位置：** `Firmware/ESP8266/MicroPython/main.py`
**程式碼行號：** 第 196 – 200 行
**說明：**
將讀取到的傳感器數值打包為 JSON，並透過 UDP 廣播至子網 (Subnet Broadcast)。

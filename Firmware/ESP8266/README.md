# ESP8266 (ESP12F) 4-DOF 機械手臂與多感測器韌體

本專案將 ESP8266 (ESP12F/NodeMCU) 轉變為全功能的機械手臂控制與感測中心。

**主要功能：**
*   🦾 **4軸機械手臂控制**：支援 4 顆 MG90S 伺服馬達 (底座, 肩部, 肘部, 夾爪)。
*   📡 **多重感測器**：整合超音波 (HC-SR04)、溫濕度 (DHT)、震動感測。
*   📶 **UDP 通訊**：透過 WiFi UDP (Port 4211) 與 PC Client 進行低延遲通訊。

---

## 🔧 硬體接線 (NodeMCU D1-D8 全滿載)

**注意：** 此配置剛好用滿 ESP12F 所有可用 GPIO。請務必嚴格遵守此接線表，否則可能導致 **無法開機** (Boot Failure)。

| 裝置 | 功能 | ESP GPIO | NodeMCU Pin | 注意事項 |
| :--- | :--- | :--- | :--- | :--- |
| **馬達 1** | 底座 (Base) | GPIO 5 | **D1** | |
| **馬達 2** | 肩部 (Shoulder)| GPIO 4 | **D2** | |
| **馬達 3** | 肘部 (Elbow) | GPIO 0 | **D3** | **開機必須為 HIGH** (接 Servo 訊號通常安全) |
| **馬達 4** | 夾爪 (Gripper) | GPIO 2 | **D4** | **開機必須為 HIGH** (板載 LED, 接 Servo 安全) |
| **感測器** | 超音波 Echo | GPIO 14| **D5** | |
| **感測器** | 震動 (Vibration)| GPIO 12| **D6** | |
| **感測器** | 溫濕度 (DHT) | GPIO 13| **D7** | |
| **感測器** | 超音波 Trig | GPIO 15| **D8** | **開機必須為 LOW** (接 Trig 很安全) |

---

## 🚀 軟體安裝

### 1. Arduino IDE 設定
*   **開發板**: `Generic ESP8266 Module` 或 `NodeMCU 1.0 (ESP-12E)`
*   **Flash Mode**: `DIO` (重要！)

### 2. 必要函式庫 (Library)
請在 Arduino Library Manager (`Ctrl+Shift+I`) 安裝以下函式庫：
1.  **DHT sensor library** (by Adafruit)
2.  **Adafruit Unified Sensor** (by Adafruit)

### 3. 上傳
開啟 `esp12f_ultrasonic/esp12f_ultrasonic.ino` 並上傳。

---

## 📡 UDP 通訊協定 (Port 4211)

### 接收指令 (PC -> ESP)
格式：JSON 字串
```json
{"base":90, "shoulder":45, "elbow":90, "gripper":0}
```
*   數值範圍：0 ~ 180 度
*   可以只發送部分欄位，例如 `{"gripper": 180}`

### 回傳數據 (ESP -> PC)
格式：JSON 字串 (廣播至 255.255.255.255)
頻率：每 200ms 一次
```json
{
    "dist": 25.4,   // 距離 (cm), -1 代表超出範圍
    "temp": 28.5,   // 溫度 (°C)
    "humid": 60.0,  // 濕度 (%)
    "vib": 1        // 震動偵測 (0:靜止, 1:震動)
}
```

---

## ⚡ 故障排除

*   **無法開機 (藍燈長亮或是沒反應)**：檢查 D3, D4, D8 接線。拔掉所有外部設備重新上快確認是否為電路問題。
*   **編譯錯誤 "DHT.h missing"**：請確認已安裝 DHT library。
*   **馬達抖動**：供電不足。建議馬達使用獨立 5V 電源，不要直接由 ESP8266 供電。

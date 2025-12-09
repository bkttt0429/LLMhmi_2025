# ESP8266 (ESP12F) 超音波感測器韌體

ESP8266 微控制器韌體，負責：
- 📏 HC-SR04 超音波測距
- 📡 UDP 資料傳輸至 PC
- ⚡ 低功耗運作

---

## 🔧 硬體規格

- **MCU**: ESP8266 (ESP12F) @ 80MHz
- **Sensor**: HC-SR04 超音波模組
- **Range**: 2cm ~ 400cm
- **Accuracy**: ±3mm
- **Update Rate**: 10Hz

---

## 🚀 快速開始

### 1. Arduino IDE 設定
1. 安裝 ESP8266 Board Manager
2. 選擇開發板: `Generic ESP8266 Module`
3. 選擇 Port: `COM4` (視情況而定)

### 2. 腳位連接
```
HC-SR04    →  ESP8266 (ESP12F)
VCC        →  3.3V
GND        →  GND
TRIG       →  GPIO 12 (D6)
ECHO       →  GPIO 14 (D5)
```

### 3. 上傳程式
```arduino
// 開啟 esp12f_ultrasonic.ino
// 修改 Wi-Fi 設定
// 上傳至 ESP12F
```

---

## 📡 通訊協定

### UDP 廣播
- **Port**: 4211
- **頻率**: 10Hz
- **格式**: ASCII 字串
- **範例**: `"25.3"` (cm)

### 目標 IP
廣播至區域網路，PC 端監聽 UDP 4211 port

---

## 📁 檔案（待補充）

```
ESP8266/
└── esp12f_ultrasonic.ino  # Arduino 程式 (待移入)
```

> ⚠️ **注意**: ESP8266 的 .ino 檔案需要手動移入此資料夾

---

## ⚡ 效能參數

- **取樣率**: 10Hz
- **平均延遲**: < 100ms
- **功耗**: ~80mA (Wi-Fi 開啟)

---

## 🐛 常見問題

### Q: 測距不穩定
A: 確保超音波感測器與物體垂直，避免軟質表面

### Q: UDP 資料未收到
A: 檢查 ESP8266 與 PC 是否在同一網段

---

**最後更新**: 2025-12-09  
**Arduino IDE 版本**: 2.x  
**ESP8266 Core 版本**: 3.x

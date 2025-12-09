# Firmware 韌體目錄

此目錄包含專案所有的嵌入式韌體程式。

---

## 📁 目錄結構

```
Firmware/
├── ESP32_S3/          # ESP32-S3 CAM 韌體 (ESP-IDF)
│   ├── main/          # 主程式碼
│   ├── CMakeLists.txt # 構建配置
│   ├── sdkconfig      # ESP-IDF 設定
│   └── README.md      # 詳細說明
│
└── ESP8266/           # ESP8266 (ESP12F) 超音波韌體 (Arduino)
    └── README.md      # 詳細說明
```

---

## 🎯 各韌體功能

### ESP32-S3 CAM
- 📷 影像串流 (MJPEG, 480p @ 20-25 FPS)
- 🚗 差速驅動馬達控制
- 📡 UDP 裝置廣播
- 💡 補光燈控制

### ESP8266 (ESP12F)
- 📏 超音波測距 (HC-SR04)
- 📡 UDP 資料傳輸
- ⚡ 低功耗運作

---

## 🚀 快速開始

### ESP32-S3
```powershell
cd Firmware\ESP32_S3
idf.py build
idf.py -p COM3 flash monitor
```

### ESP8266
```powershell
# 使用 Arduino IDE
# 開啟 Firmware/ESP8266/esp12f_ultrasonic.ino
# 上傳至 ESP12F
```

---

## 📚 詳細文件

- [ESP32-S3 README](ESP32_S3/README.md)
- [ESP8266 README](ESP8266/README.md)

---

**最後更新**: 2025-12-09

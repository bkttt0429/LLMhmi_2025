# ESP32-CAM 遠端監控系統 (PC Client)

> 🚀 **高性能視訊串流 + YOLOv13 AI 物件偵測 + Xbox 手把控制**

## 📋 概述

這是一個為 ESP32-CAM 優化的 PC 端監控系統，具備：
- ✅ **低延遲視訊串流** (~50-100ms)
- ✅ **即時 AI 物件偵測** (YOLOv13)
- ✅ **多種控制方式** (鍵盤 WASD / Xbox 手把)
- ✅ **雙網卡支援** (WiFi + 有線分離)
- ✅ **自動重連機制** (Exponential backoff)

---

## 🎯 核心特性

### 1. 自訂 MJPEG 串流引擎

專為 ESP32-CAM 設計的 `mjpeg_reader.py`：
- **JPEG 邊界檢測** - 解決 TCP 封包碎片化問題
- **背景線程讀取** - 防止 socket buffer 溢出
- **Exponential backoff 重連** - 智能重試策略 (1s → 2s → 4s → ... → 30s)
- **網路介面綁定** - 支援雙網卡環境

### 2. AI 物件偵測優化

- **跳幀處理** - 每 5 幀處理 1 次 (降低 80% 運算)
- **結果快取** - JPEG bytes 直接重用，避免重複編碼
- **GPU 加速** - 支援 CUDA (需正確安裝 PyTorch)
- **實時標註** - 在視訊上疊加偵測框和標籤

### 3. 效能指標

| 場景 | FPS | 延遲 | CPU 使用 |
|------|-----|------|---------|
| 純視訊 (無 AI) | ~24-25 | ~50ms | 低 |
| AI 開啟 (CPU) | ~15-18 | ~100ms | 中 |
| AI 開啟 (GPU) | ~20-24 | ~70ms | 低 |

---

## 🛠️ 安裝步驟

### 1. 前置需求

- **Python 3.11+** (推薦使用 Anaconda)
- **CUDA 11.8** (如需 GPU 加速)
- **ESP32-CAM** (已刷入 MJPEG stream 韌體)

### 2. 建立環境

```bash
# 建立 conda 環境
conda create -n yolov13 python=3.11
conda activate yolov13

# 安裝依賴
pip install flask flask-socketio requests opencv-python numpy pillow pygame

# 安裝 PyTorch (GPU 版本)
pip install torch==2.5.1+cu118 torchvision==0.20.1+cu118 torchaudio==2.5.1+cu118 --index-url https://download.pytorch.org/whl/cu118

# 或 CPU 版本 (不建議用於 AI)
# pip install torch torchvision torchaudio
```

### 3. 安裝 Tailwind CSS (前端樣式)

```bash
cd PC_Client
npm install
npx tailwindcss -i ./static/css/input.css -o ./static/css/output.css --watch
```

### 4. 下載 YOLOv13 模型

放置以下模型檔案到 `PC_Client/` 目錄：
- `yolov13n.pt` (輕量級, ~10MB)
- `yolov13s.pt` (標準, ~37MB)
- `yolov13l.pt` (高精度, ~112MB)

---

## 🚀 使用方法

### 啟動 Server

```bash
python web_server.py
```

### 瀏覽器訪問

開啟瀏覽器訪問: **http://127.0.0.1:5000**

### ESP32-CAM 設定

1. 確保 ESP32 已連接 WiFi
2. 訪問 ESP32 web 介面（如 `http://10.243.115.133`）
3. 點擊 **"Start Stream"** 啟動視訊
4. PC Client 會自動連接 `http://10.243.115.133:81/stream`

---

## 🎮 控制方式

### 鍵盤控制 (WASD)

| 按鍵 | 功能 |
|------|------|
| W | 前進 |
| S | 後退 |
| A | 左轉 |
| D | 右轉 |
| Space | 煞車 |

### Xbox 手把

- **左搖桿** - 移動控制
- 自動偵測連接，無需額外設定

---

## 📁 專案結構

```
PC_Client/
├── web_server.py              # Flask 主伺服器
├── video_process.py           # 視訊處理進程 (multiprocessing)
├── mjpeg_reader.py            # 自訂 MJPEG 串流讀取器 ⭐
├── ai_detector.py             # YOLOv13 物件偵測
├── network_utils.py           # 網路工具 (雙網卡綁定)
├── config.py                  # 配置檔案
├── templates/
│   └── index.html             # Web UI
├── static/
│   └── css/
│       ├── input.css          # Tailwind 原始檔
│       └── output.css         # 編譯後 CSS
└── yolov13-main/              # YOLO 模型庫
```

---

## ⚙️ 配置說明

編輯 `config.py`:

```python
# Web Server
WEB_HOST = '0.0.0.0'
WEB_PORT = 5000

# ESP32-CAM
DEFAULT_STREAM_IP = '10.243.115.133'
DEFAULT_STREAM_URL = 'http://10.243.115.133:81/stream'

# AI 設定
AI_PROCESS_EVERY_N_FRAMES = 5  # 每 5 幀處理 1 次
```

---

## 🐛 常見問題

### 1. CUDA 無法使用 (AI 使用 CPU)

**問題**: 日誌顯示 `⚠️ AI Device: CPU`

**解決**:
```bash
# 確認 CUDA 可用
python -c "import torch; print(torch.cuda.is_available())"

# 如果返回 False，重新安裝 GPU 版本
pip install torch==2.5.1+cu118 torchvision==0.20.1+cu118 --index-url https://download.pytorch.org/whl/cu118 --force-reinstall
```

### 2. 視訊無法連接

**檢查清單**:
- [ ] ESP32 是否已啟動 stream (`http://ESP32_IP:81/stream` 可訪問)
- [ ] 防火牆是否阻擋
- [ ] IP 位址是否正確 (檢查 `config.py`)

### 3. FPS 過低

**優化建議**:
- 降低 AI 模型大小 (使用 `yolov13n.pt`)
- 增加跳幀率 (`AI_PROCESS_EVERY_N_FRAMES = 10`)
- 啟用 GPU 加速

---

## 📊 性能優化歷程

### 🔄 版本演進

#### v1.0 - 基礎版本
- 使用 VidGear CamGear
- FPS: ~20 (無 AI), ~1-5 (有 AI)
- 問題: 高延遲、記憶體使用高

#### v2.0 - 自訂 MJPEG Reader ⭐
- 移除 VidGear, 實作 `mjpeg_reader.py`
- FPS: ~24-25 (無 AI), ~15-18 (有 AI)
- 改善: 延遲 ↓60%, 記憶體 ↓80%

#### v2.1 - AI 跳幀優化
- 實作每 N 幀處理策略
- FPS: ~24 (無 AI), ~18-22 (有 AI)
- 改善: CPU 使用 ↓70%

#### v2.2 - JPEG bytes 快取 (當前)
- AI 結果快取為 JPEG, 避免重複編碼
- FPS: ~24 (無 AI), ~20-24 (有 AI, GPU)
- 改善: 編碼開銷 ↓80%

---

## 🤝 貢獻

歡迎提交 Issue 和 Pull Request！

## 📄 授權

MIT License

---

## 🔗 相關資源

- [YOLOv13 官方](https://github.com/ultralytics/ultralytics)
- [ESP32-CAM 教學](https://randomnerdtutorials.com/esp32-cam-video-streaming-web-server-camera-home-assistant/)
- [Flask 文件](https://flask.palletsprojects.com/)

---

**最後更新**: 2025-12-09

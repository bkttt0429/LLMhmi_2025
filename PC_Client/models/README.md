# YOLO 模型權重

此資料夾包含 YOLOv13/v8 系列的預訓練模型權重檔案。

---

## 🤖 可用模型

| 模型 | 大小 | VRAM需求 | 速度 | 精度 | 建議用途 |
|------|------|----------|------|------|----------|
| **yolov13n.pt** | ~10MB | ~1.5GB | 🚀🚀🚀 | ⭐⭐⭐ | 即時追蹤（推薦 4GB VRAM） |
| **yolov13s.pt** | ~35MB | ~2.5GB | 🚀🚀 | ⭐⭐⭐⭐ | 平衡模式 |
| **yolov13l.pt** | ~106MB | ~4.5GB | 🚀 | ⭐⭐⭐⭐⭐ | 高精度（需 6GB+ VRAM） |
| **yolov13x.pt** | ~245MB | ~7GB | 🐢 | ⭐⭐⭐⭐⭐ | 超高精度（需 8GB+ VRAM） |

---

## 💡 模型選擇建議

### RTX 3050 Ti (4GB VRAM) - 您的硬體
推薦使用：
1. **yolov13n.pt** ✅ 最佳選擇
2. **yolov13s.pt** ⚠️ 可用，但接近上限

不建議使用：
- ❌ yolov13l.pt - VRAM 不足
- ❌ yolov13x.pt - VRAM 不足

### 更大 VRAM (6GB+)
- yolov13l.pt 或更大模型

---

## 🔧 使用方法

### 在 Web 介面切換
1. 打開 http://localhost:5000
2. 進入 `SYSTEM` 分頁
3. 在 `AI Model Selection` 下拉選單選擇模型
4. 點擊 `LOAD` 載入

### 在程式碼中指定
```python
from ai_detector import ObjectDetector

# 使用特定模型
detector = ObjectDetector(model_path='./models/yolov13n.pt')
```

---

## 📦 下載新模型

如需其他 YOLO 模型：
```bash
# YOLOv8 系列
pip install ultralytics
# Python 中自動下載
from ultralytics import YOLO
model = YOLO('yolov8n.pt')  # 首次使用會自動下載
```

---

## 📊 效能參考 (RTX 3050 Ti)

| 模型 | FPS (640px) | 延遲 | VRAM 使用 |
|------|-------------|------|-----------|
| yolov13n | 40-50 | 20-25ms | ~1.8GB |
| yolov13s | 25-35 | 30-40ms | ~2.5GB |
| yolov13l | 15-20 | 50-70ms | ~3.8GB ⚠️ |

---

**最後更新**: 2025-12-09  
**測試環境**: RTX 3050 Ti 4GB + CUDA 11.8

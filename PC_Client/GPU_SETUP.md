# GPU 加速配置指南 🚀

## ✅ 當前 GPU 狀態

**檢測結果：** 
- GPU: **NVIDIA GeForce RTX 3050 Ti Laptop GPU**
- VRAM: **4.00 GB**
- CUDA: **11.8**
- Compute Capability: **8.6** (支援 Tensor Core)
- cuDNN: **v9.1.0**
- **Flash Attention**: ✅ **已啟用** (SDPA)

**最新優化 (v16.1)**:
```
✅ Tensor Core 優化已啟用
✅ Flash Attention (SDPA) 已啟用
   └─ Flash SDP: Enabled
   └─ Memory Efficient SDP: Enabled  
   └─ Math SDP: Enabled (Fallback)
```

---

## 🎯 推薦配置

### YOLOv13 模型選擇

根據你的 **4GB VRAM**，推薦使用：

| 模型 | VRAM 需求 | 速度 | 精度 | 建議場景 |
|------|-----------|------|------|----------|
| **yolov8n.pt** | ~1.5GB | 🚀🚀🚀 | ⭐⭐⭐ | 即時追蹤（推薦） |
| **yolov8s.pt** | ~2.5GB | 🚀🚀 | ⭐⭐⭐⭐ | 平衡模式 |
| **yolov8m.pt** | ~3.8GB | 🚀 | ⭐⭐⭐⭐⭐ | 高精度（謹慎） |

⚠️ **不建議使用**: `yolov13l.pt`, `yolov13x.pt` (需 6GB+ VRAM)

### 輸入尺寸建議
- **320px**: 極速模式（60+ FPS）
- **640px**: 平衡模式（30-40 FPS）- 推薦
- **1280px**: 精確模式（不建議，VRAM 不足）

---

## 🚀 快速啟動

### 方法 1: 使用啟動腳本（推薦）
```powershell
# 雙擊或執行
.\run_server.bat
```

### 方法 2: 手動啟動
```powershell
conda activate yolov13
$env:KMP_DUPLICATE_LIB_OK="TRUE"
python web_server.py
```

---

## 🔧 工具腳本

### 1. GPU 狀態檢測
```powershell
python test_gpu.py
```
**輸出示例：**
```
✅ CUDA 可用: True
📊 GPU: NVIDIA GeForce RTX 3050 Ti Laptop GPU
💾 VRAM: 4.00 GB
🧪 GPU 矩陣運算成功 (94.17 ms)
```

### 2. 即時 GPU 監控
```powershell
python monitor_gpu.py
```
**功能：**
- 即時 VRAM 使用率
- 彩色進度條
- 自動刷新（1 秒間隔）

### 3. CUDA 環境診斷
```powershell
python diagnose_cuda.py
```

---

## 🐛 常見問題

### ❌ 問題 1: `OMP: Error #15`
**錯誤訊息：**
```
Initializing libiomp5md.dll, but found libiomp5md.dll already initialized.
```

**解決方案：**
1. **自動修復**（已應用）：`ai_detector.py` 已內建修復
2. **手動啟動**：使用 `run_server.bat`
3. **臨時設置**：
   ```powershell
   $env:KMP_DUPLICATE_LIB_OK="TRUE"
   ```

---

### ❌ 問題 2: CUDA 不可用
**原因：** 在錯誤的 conda 環境

**解決：**
```powershell
conda activate yolov13  # 確保使用正確環境
python test_gpu.py
```

---

### ❌ 問題 3: VRAM 不足
**症狀：** `RuntimeError: CUDA out of memory`

**解決方案：**
1. **切換更小模型**：`yolov8n.pt` 或 `yolov8s.pt`
2. **降低輸入尺寸**：
   ```python
   # ai_detector.py
   self.input_size = 320  # 從 640 降至 320
   ```
3. **啟用跳幀**：
   ```python
   self.process_every_n = 2  # 每 2 幀處理一次
   ```

---

## 📊 效能優化技巧

### 1. 啟用 cuDNN Benchmark
```python
# ai_detector.py (已自動啟用)
torch.backends.cudnn.benchmark = True
```
**效果：** 加速 15-30%

### 2. 使用半精度推論（FP16）
```python
# ai_detector.py (已啟用)
results = self.model.track(
    frame,
    half=True  # GPU 自動啟用 FP16
)
```
**效果：** 
- 速度 ↑ 40-60%
- VRAM ↓ 50%

### 3. 清空 GPU 快取
```python
torch.cuda.empty_cache()
```

---

## 🎮 YOLOv13 實際使用

### 啟動 AI 偵測
```python
# 在 web_server.py 或 video_process.py 中
from ai_detector import ObjectDetector

detector = ObjectDetector(model_path='./yolov8n.pt')
frame, detections, control = detector.detect(frame)
```

### 效能監控
運行時 HUD 顯示：
- FPS: 當前/平均
- Device: CUDA
- Model: yolov8n.pt
- Objects: 偵測數量
- Control: v, w 控制量

---

## 📈 預期效能

| 模型 | 解析度 | FPS (RTX 3050 Ti) | VRAM 使用 |
|------|--------|-------------------|-----------|
| yolov8n | 320 | **60-80** | ~1.2GB |
| yolov8n | 640 | **40-50** | ~1.8GB |
| yolov8s | 640 | **25-35** | ~2.5GB |
| yolov8m | 640 | **15-20** | ~3.5GB |

---

## 🔍 驗證步驟

1. **測試 CUDA**
   ```powershell
   python test_gpu.py
   ```
   ✅ 應該顯示 "CUDA Available: True"

2. **測試 AI 偵測**
   ```powershell
   python web_server.py
   # 開啟瀏覽器 http://localhost:5000
   # 啟用 AI 偵測功能
   ```

3. **監控 GPU**
   ```powershell
   # 另開終端
   python monitor_gpu.py
   ```

---

## 📞 支援

遇到問題？檢查：
1. `nvidia-smi` - 確認驅動正常
2. `conda list | findstr torch` - 確認 PyTorch 版本
3. 查看本文的「常見問題」章節

---

**最後更新：** 2025-12-09  
**GPU 配置版本：** v1.0  
**測試環境：** RTX 3050 Ti (4GB) + CUDA 11.8 + PyTorch 2.5.1

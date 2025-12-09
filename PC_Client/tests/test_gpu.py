#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""GPU 狀態檢測工具"""

import torch
import sys

print("=" * 60)
print("🔍 PyTorch GPU 檢測報告")
print("=" * 60)

# 1. CUDA 可用性
cuda_available = torch.cuda.is_available()
print(f"\n✅ CUDA 可用: {cuda_available}")

if not cuda_available:
    print("\n❌ CUDA 不可用，可能原因:")
    print("   1. 未安裝 NVIDIA GPU 驅動程式")
    print("   2. 未安裝 CUDA Toolkit")
    print("   3. PyTorch 版本不支援 CUDA (CPU-only)")
    print("\n💡 修復方法:")
    print("   - 檢查驅動: nvidia-smi")
    print("   - 重新安裝 PyTorch: pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121")
    sys.exit(1)

# 2. CUDA 版本
print(f"   └─ CUDA 版本: {torch.version.cuda}")

# 3. cuDNN 版本
if torch.backends.cudnn.is_available():
    print(f"   └─ cuDNN 版本: {torch.backends.cudnn.version()}")
    print(f"   └─ cuDNN Benchmark: {torch.backends.cudnn.benchmark}")

# 4. GPU 數量
gpu_count = torch.cuda.device_count()
print(f"\n🎮 GPU 數量: {gpu_count}")

# 5. GPU 詳細資訊
for i in range(gpu_count):
    print(f"\n📊 GPU {i} 詳細資訊:")
    print(f"   ├─ 名稱: {torch.cuda.get_device_name(i)}")
    
    props = torch.cuda.get_device_properties(i)
    print(f"   ├─ 總記憶體: {props.total_memory / 1024**3:.2f} GB")
    print(f"   ├─ 多處理器數量: {props.multi_processor_count}")
    print(f"   ├─ Compute Capability: {props.major}.{props.minor}")
    
    # 即時記憶體使用
    allocated = torch.cuda.memory_allocated(i) / 1024**2
    reserved = torch.cuda.memory_reserved(i) / 1024**2
    print(f"   ├─ 已分配記憶體: {allocated:.2f} MB")
    print(f"   └─ 已保留記憶體: {reserved:.2f} MB")

# 6. 測試 GPU 運算
print("\n🧪 測試 GPU 運算...")
try:
    # 創建測試張量
    x = torch.rand(1000, 1000).cuda()
    y = torch.rand(1000, 1000).cuda()
    
    # 執行矩陣乘法
    import time
    start = time.time()
    z = torch.matmul(x, y)
    torch.cuda.synchronize()  # 等待 GPU 完成
    elapsed = time.time() - start
    
    print(f"   ✅ GPU 矩陣運算成功 (1000x1000)")
    print(f"   └─ 耗時: {elapsed*1000:.2f} ms")
    
    # 清理
    del x, y, z
    torch.cuda.empty_cache()
    
except Exception as e:
    print(f"   ❌ GPU 運算失敗: {e}")

# 7. PyTorch 版本資訊
print(f"\n📦 PyTorch 版本: {torch.__version__}")
print(f"   └─ 建置版本: {torch.version.debug if hasattr(torch.version, 'debug') else 'N/A'}")

# 8. 環境建議
print("\n💡 YOLOv13 最佳配置:")
if gpu_count > 0:
    vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
    if vram < 4:
        print("   ⚠️ VRAM < 4GB，建議:")
        print("      - 使用 yolov8n.pt 或 yolov8s.pt")
        print("      - 降低輸入尺寸 (320)")
    elif vram >= 8:
        print("   ✅ VRAM >= 8GB，可使用:")
        print("      - yolov13l.pt 或 yolov13x.pt")
        print("      - 輸入尺寸 640 或更高")
    else:
        print("   ✅ VRAM 4-8GB，建議:")
        print("      - yolov8m.pt 或 yolov13s.pt")
        print("      - 輸入尺寸 640")

print("\n" + "=" * 60)
print("✅ 檢測完成")
print("=" * 60)

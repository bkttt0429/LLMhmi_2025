"""
CUDA 診斷腳本 - 檢查 PyTorch CUDA 配置
"""
import torch
import sys

print("=" * 60)
print("🔍 PyTorch CUDA 診斷")
print("=" * 60)

print(f"\n📦 PyTorch 版本: {torch.__version__}")
print(f"🐍 Python 版本: {sys.version}")

print(f"\n🎮 CUDA 可用性:")
print(f"   torch.cuda.is_available(): {torch.cuda.is_available()}")

if torch.cuda.is_available():
    print(f"\n✅ CUDA 已啟用")
    print(f"   CUDA 版本: {torch.version.cuda}")
    print(f"   cuDNN 版本: {torch.backends.cudnn.version()}")
    print(f"   GPU 數量: {torch.cuda.device_count()}")
    
    for i in range(torch.cuda.device_count()):
        print(f"\n   GPU {i}:")
        print(f"      名稱: {torch.cuda.get_device_name(i)}")
        props = torch.cuda.get_device_properties(i)
        print(f"      VRAM: {props.total_memory / 1024**3:.1f} GB")
        print(f"      Compute Capability: {props.major}.{props.minor}")
    
    # 測試 CUDA 操作
    try:
        x = torch.zeros(1).cuda()
        print(f"\n✅ CUDA 張量創建成功")
        del x
        torch.cuda.empty_cache()
    except Exception as e:
        print(f"\n❌ CUDA 張量創建失敗: {e}")
        
else:
    print(f"\n❌ CUDA 不可用")
    print(f"\n可能的原因:")
    print(f"   1. PyTorch 未編譯 CUDA 支援 (CPU-only 版本)")
    print(f"   2. CUDA 驅動未安裝或版本不匹配")
    print(f"   3. 環境變數設定錯誤")
    print(f"\n檢查步驟:")
    print(f"   1. 執行: python -c \"import torch; print(torch.version.cuda)\"")
    print(f"   2. 執行: nvidia-smi")
    print(f"   3. 重新安裝 PyTorch with CUDA:")
    print(f"      pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118")

print("\n" + "=" * 60)

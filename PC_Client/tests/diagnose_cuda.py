#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""CUDA 診斷工具"""

import os
import sys

print("=" * 70)
print("🔍 CUDA 環境診斷")
print("=" * 70)

# 1. 檢查環境變數
print("\n📂 CUDA 相關環境變數:")
cuda_vars = ['CUDA_PATH', 'CUDA_HOME', 'PATH', 'LD_LIBRARY_PATH']
for var in cuda_vars:
    value = os.environ.get(var, 'NOT SET')
    if var == 'PATH':
        paths = value.split(';')
        cuda_paths = [p for p in paths if 'cuda' in p.lower()]
        print(f"   {var} (CUDA 相關):")
        for p in cuda_paths[:5]:  # 只顯示前 5 個
            print(f"      - {p}")
    else:
        print(f"   {var}: {value}")

# 2. 檢查 PyTorch
print("\n📦 PyTorch 資訊:")
try:
    import torch
    print(f"   ✅ PyTorch 版本: {torch.__version__}")
    print(f"   ├─ 安裝路徑: {torch.__file__}")
    print(f"   ├─ CUDA 編譯版本: {torch.version.cuda}")
    print(f"   ├─ cuDNN 版本: {torch.backends.cudnn.version() if torch.backends.cudnn.is_available() else 'N/A'}")
    print(f"   └─ CUDA 可用: {torch.cuda.is_available()}")
    
    if not torch.cuda.is_available():
        print("\n🔧 詳細錯誤檢查:")
        try:
            # 嘗試訪問 CUDA
            _ = torch.cuda.device_count()
        except Exception as e:
            print(f"   ❌ CUDA 初始化錯誤: {e}")
            print(f"   錯誤類型: {type(e).__name__}")
            
except ImportError as e:
    print(f"   ❌ PyTorch 未安裝: {e}")

# 3. 檢查 CUDA DLL
print("\n📚 CUDA DLL 檢查:")
cuda_dlls = ['cudart64_118.dll', 'cublas64_11.dll', 'cudnn64_8.dll']
cuda_path = os.environ.get('CUDA_PATH', '')

if cuda_path:
    bin_path = os.path.join(cuda_path, 'bin')
    print(f"   CUDA Bin 路徑: {bin_path}")
    
    if os.path.exists(bin_path):
        for dll in cuda_dlls:
            dll_path = os.path.join(bin_path, dll)
            exists = "✅" if os.path.exists(dll_path) else "❌"
            print(f"   {exists} {dll}")
    else:
        print(f"   ❌ CUDA Bin 路徑不存在")
else:
    print("   ❌ CUDA_PATH 環境變數未設定")

# 4. Python 環境
print(f"\n🐍 Python 環境:")
print(f"   版本: {sys.version}")
print(f"   執行檔: {sys.executable}")
print(f"   虛擬環境: {os.environ.get('CONDA_DEFAULT_ENV', 'None')}")

# 5. 建議
print("\n" + "=" * 70)
print("💡 修復建議:")
print("=" * 70)

import torch
if not torch.cuda.is_available():
    print("✅ 方案 1: 重新安裝匹配的 PyTorch (推薦)")
    print("   conda install pytorch torchvision torchaudio pytorch-cuda=11.8 -c pytorch -c nvidia")
    print("\n✅ 方案 2: 使用 pip 安裝")
    print("   pip uninstall torch torchvision torchaudio")
    print("   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118")
    print("\n✅ 方案 3: 檢查環境變數")
    print("   確保 CUDA_PATH 指向正確的 CUDA 安裝目錄")
    print("   確保 PATH 包含 %CUDA_PATH%\\bin")
else:
    print("🎉 CUDA 已正常工作！")

print("=" * 70)

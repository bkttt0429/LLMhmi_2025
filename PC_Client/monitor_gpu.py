#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""即時 GPU 使用率監控工具"""

import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

import torch
import time
import sys
from datetime import datetime

def clear_screen():
    """清除終端畫面"""
    os.system('cls' if os.name == 'nt' else 'clear')

def format_bytes(bytes_val):
    """格式化位元組大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} TB"

def get_gpu_usage():
    """獲取 GPU 使用資訊"""
    if not torch.cuda.is_available():
        return None
    
    device = 0
    props = torch.cuda.get_device_properties(device)
    
    # 記憶體資訊
    total_memory = props.total_memory
    allocated = torch.cuda.memory_allocated(device)
    reserved = torch.cuda.memory_reserved(device)
    free = total_memory - allocated
    
    # 計算使用率
    usage_percent = (allocated / total_memory) * 100
    
    return {
        'name': torch.cuda.get_device_name(device),
        'total': total_memory,
        'allocated': allocated,
        'reserved': reserved,
        'free': free,
        'usage_percent': usage_percent,
        'compute_capability': f"{props.major}.{props.minor}",
        'multi_processors': props.multi_processor_count
    }

def draw_progress_bar(percent, width=50):
    """繪製進度條"""
    filled = int(width * percent / 100)
    bar = '█' * filled + '░' * (width - filled)
    
    # 根據使用率選擇顏色（ANSI 顏色碼）
    if percent < 50:
        color = '\033[92m'  # 綠色
    elif percent < 80:
        color = '\033[93m'  # 黃色
    else:
        color = '\033[91m'  # 紅色
    
    reset = '\033[0m'
    return f"{color}{bar}{reset} {percent:.1f}%"

def monitor_gpu(interval=1.0):
    """主監控循環"""
    print("🚀 啟動 GPU 監控...")
    print("按 Ctrl+C 停止\n")
    time.sleep(1)
    
    try:
        while True:
            clear_screen()
            
            # 標題
            print("=" * 80)
            print(f"🎮 GPU 即時監控 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 80)
            
            # 獲取 GPU 資訊
            gpu_info = get_gpu_usage()
            
            if gpu_info is None:
                print("\n❌ CUDA 不可用")
                break
            
            # 顯示基本資訊
            print(f"\n📊 GPU 資訊")
            print(f"   名稱: {gpu_info['name']}")
            print(f"   Compute Capability: {gpu_info['compute_capability']}")
            print(f"   多處理器數量: {gpu_info['multi_processors']}")
            
            # 記憶體使用
            print(f"\n💾 VRAM 使用狀況")
            print(f"   總容量: {format_bytes(gpu_info['total'])}")
            print(f"   已使用: {format_bytes(gpu_info['allocated'])}")
            print(f"   已保留: {format_bytes(gpu_info['reserved'])}")
            print(f"   可用:   {format_bytes(gpu_info['free'])}")
            
            # 使用率進度條
            print(f"\n📈 使用率")
            print(f"   {draw_progress_bar(gpu_info['usage_percent'])}")
            
            # PyTorch 資訊
            print(f"\n🔧 PyTorch 環境")
            print(f"   版本: {torch.__version__}")
            print(f"   CUDA 版本: {torch.version.cuda}")
            print(f"   cuDNN Benchmark: {torch.backends.cudnn.benchmark}")
            
            # 提示
            print("\n" + "=" * 80)
            print(f"更新間隔: {interval}s | 按 Ctrl+C 停止")
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\n\n✅ 監控已停止")
        sys.exit(0)

if __name__ == "__main__":
    # 檢查參數
    interval = 1.0
    if len(sys.argv) > 1:
        try:
            interval = float(sys.argv[1])
        except ValueError:
            print("⚠️ 無效的間隔時間，使用預設值 1.0 秒")
    
    monitor_gpu(interval)

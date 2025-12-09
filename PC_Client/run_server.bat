@echo off
REM ESP32 Web Server 啟動腳本 (GPU 優化)
echo ========================================
echo ESP32 Remote Control Server
echo GPU Accelerated with CUDA 11.8
echo ========================================

REM 啟動 yolov13 環境
call conda activate yolov13
if errorlevel 1 (
    echo ❌ 無法啟動 yolov13 環境
    pause
    exit /b 1
)

REM 設置 OpenMP 環境變數（解決 libiomp5md.dll 衝突）
set KMP_DUPLICATE_LIB_OK=TRUE

REM 設置 CUDA 優化
set CUDA_LAUNCH_BLOCKING=0
set PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:128

echo.
echo ✅ 環境設置完成
echo    └─ Conda Env: yolov13
echo    └─ OpenMP Fix: Enabled
echo    └─ CUDA Memory: Optimized
echo.

REM 啟動 Flask 伺服器
echo 🚀 啟動 Web Server...
python web_server.py

pause

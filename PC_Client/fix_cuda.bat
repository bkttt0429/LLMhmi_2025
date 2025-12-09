@echo off
REM CUDA 修復腳本
echo ========================================
echo CUDA PyTorch 自動修復工具
echo ========================================

echo.
echo [1/4] 啟動 yolov13 環境...
call conda activate yolov13
if errorlevel 1 (
    echo 錯誤: 無法啟動 yolov13 環境
    pause
    exit /b 1
)

echo.
echo [2/4] 檢查當前 PyTorch 狀態...
python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA Available: {torch.cuda.is_available()}')"

echo.
echo [3/4] 重新安裝 PyTorch (CUDA 11.8)...
pip uninstall torch torchvision torchaudio -y
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

echo.
echo [4/4] 驗證安裝...
python test_gpu.py

echo.
echo ========================================
echo 修復完成！
echo ========================================
pause

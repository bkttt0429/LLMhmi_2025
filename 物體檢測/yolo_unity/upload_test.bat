@echo off
chcp 65001
cls
echo ========================================================
echo   ESP32-S3 強制上傳工具 (排除 Python 干擾)
echo ========================================================
echo.

set /p COM_PORT="請輸入 COM Port (例如 COM3): "

echo.
echo 正在編譯並上傳...
echo 注意：當看到 "Connecting..." 出現時，請隨時準備按 BOOT 鍵！
echo.

arduino-cli compile --fqbn esp32:esp32:esp32s3 esp32s3_cam --upload -p %COM_PORT% --upload-field upload.speed=115200

echo.
if %errorlevel% neq 0 (
    echo ❌ 上傳失敗！
    echo 請嘗試：拔掉 USB 重插 -> 執行此腳本 -> 當看到 Connecting 時按住 BOOT 鍵不放
) else (
    echo ✅ 上傳成功！恭喜！
)
pause
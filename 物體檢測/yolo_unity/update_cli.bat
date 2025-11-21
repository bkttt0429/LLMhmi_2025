@echo off
chcp 65001
cls
echo ==========================================
echo      正在下載最新版 Arduino CLI...
echo ==========================================

:: 1. 下載官方最新版 zip (Windows 64-bit)
curl -L -o arduino-cli.zip https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_Windows_64bit.zip

echo.
echo ==========================================
echo      正在解壓縮...
echo ==========================================

:: 2. 使用 tar 解壓縮 (Windows 10/11 內建)
tar -xf arduino-cli.zip

echo.
echo ==========================================
echo      版本驗證
echo ==========================================

:: 3. 顯示新下載的版本
arduino-cli.exe version

echo.
echo ==========================================
echo ✅ 更新完成！
echo 新的 arduino-cli.exe 已經在目前資料夾中。
echo.
echo 如果你原本將 arduino-cli 放在其他路徑（例如 System32 或 Program Files），
echo 請手動將這個新檔案複製過去覆蓋。
echo ==========================================
del arduino-cli.zip
pause
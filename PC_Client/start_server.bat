@echo off
REM 設定環境變數解決 OpenMP 衝突
set KMP_DUPLICATE_LIB_OK=TRUE

REM 啟動 Flask 伺服器
echo Starting web server...
python web_server.py

pause

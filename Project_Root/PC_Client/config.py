import os

# ========= 系統參數 =========
# ESP32 串流的預設 Port
DEFAULT_STREAM_PORT = 81
# 若已知 CAM 的 IP，可在此預先填入或透過環境變數 DEFAULT_STREAM_IP 指定，
# 方便啟動時直接嘗試連線，例如：export DEFAULT_STREAM_IP=192.168.4.1
# 預設改為 mDNS 名稱，讓未連上 USB 時也能直接嘗試串流
DEFAULT_STREAM_IP = os.environ.get("DEFAULT_STREAM_IP", "boebot.local")

# Arduino CLI 路徑 (燒錄用)
SKETCH_DIR = "../esp32s3_cam"          
SKETCH_NAME = "esp32s3_cam.ino"
SOURCE_INO = "../code.ino"             
FQBN = ("esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,PartitionScheme=fatflash,UploadSpeed=921600")
ESP32_URL = "https://espressif.github.io/arduino-esp32/package_esp32_index.json"

# Serial 設定
BAUD_RATE = 115200

# ========= 網頁伺服器設定 =========
WEB_HOST = "0.0.0.0"  # 允許從區域網路連線
WEB_PORT = 5000

# ========= 遙控指令 =========
CMD_FORWARD = 'F'
CMD_BACKWARD = 'B'
CMD_LEFT = 'L'
CMD_RIGHT = 'R'
CMD_STOP = 'S'
CMD_LIGHT_ON = 'W'
CMD_LIGHT_OFF = 'w'

# ========= GUI 風格 (PySide6 專用) =========
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 850

COLOR_BG = "#0f172a"
COLOR_PANEL = "#1e293b"
COLOR_ACCENT = "#06b6d4"
COLOR_GLOW = "#22d3ee"
COLOR_ALERT = "#ef4444"
COLOR_AI = "#d946ef"

DARK_STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {COLOR_BG};
    color: #e2e8f0;
    font-family: "Segoe UI", "Consolas", sans-serif;
    font-size: 14px;
}}
/* ... (保留您原本的樣式表內容) ... */
"""

# 環境變數
os.environ["PYTHONIOENCODING"] = "utf-8"
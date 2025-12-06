import os

# ========= 系統參數 =========
# ESP32-S3 Integrated Mode
DEFAULT_STREAM_PORT = 81  # ESP32 視頻流運行在 port 81
CAMERA_DISCOVERY_PORT = 4213 # UDP Broadcast Port for Discovery

# ========= 🚗 車子控制 & 串流設定 (Integrated ESP32-S3) =========
# 整合後，車子控制和影像串流使用同一個 IP
DEFAULT_CAR_IP = "10.243.115.133"  # 更新為實際 ESP32 IP
DEFAULT_STREAM_IP = "10.243.115.133"  # 更新為實際 ESP32 IP

# 多個串流來源（按優先順序）
DEFAULT_STREAM_HOSTS = [
    "10.243.115.133",
]

# Arduino CLI 路徑 (燒錄用)
SKETCH_DIR = "../Firmware/esp32s3_integrated"
SKETCH_NAME = "esp32s3_integrated.ino"
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

# ========= GUI 風格 (PySide6 專用 - 保留) =========
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
"""

# 環境變數
os.environ["PYTHONIOENCODING"] = "utf-8"

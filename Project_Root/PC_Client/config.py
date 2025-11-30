import os

# ========= 系統參數 =========
# ESP32-S3 CAM 串流的預設 Port
DEFAULT_STREAM_PORT = 81
CAMERA_DISCOVERY_PORT = 4211

# ========= 🚗 車子控制設定 (ESP8266) =========
# 方法 1: 使用 mDNS（推薦，如果網路支援）
DEFAULT_CAR_IP = "boebot.local"

# 方法 2: 使用實際 IP（如果 mDNS 不可用）
# 請將下面這行取消註解，並填入 ESP8266 的實際 IP
# DEFAULT_CAR_IP = "192.168.43.100"  # 替換成您的 ESP8266 IP

# ========= 📹 相機串流設定 (ESP32-S3 CAM) =========
# 方法 1: 使用 mDNS
DEFAULT_STREAM_IP = os.environ.get("DEFAULT_STREAM_IP", "")

# 方法 2: 如果已知 CAM 的 IP，可直接填入
# DEFAULT_STREAM_IP = "10.164.216.133"  # 替換成您的 ESP32-S3 CAM IP

# 多個串流來源（按優先順序）
DEFAULT_STREAM_HOSTS = [
    "boebot.local",
    # 如果需要，可以在這裡加入更多備用 IP
]

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
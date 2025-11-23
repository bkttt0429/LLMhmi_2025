import os

# ========= 系統參數 =========
SKETCH_DIR = "../esp32s3_cam"          
SKETCH_NAME = "esp32s3_cam.ino"
SOURCE_INO = "../code.ino"             

FQBN = ("esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,PartitionScheme=fatflash,UploadSpeed=921600")
BAUD_RATE = 115200                  
ESP32_URL = "https://espressif.github.io/arduino-esp32/package_esp32_index.json"

DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 800

os.environ["PYTHONIOENCODING"] = "utf-8"

# ========= 遙控指令 =========
CMD_FORWARD = 'F'
CMD_BACKWARD = 'B'
CMD_LEFT = 'L'
CMD_RIGHT = 'R'
CMD_STOP = 'S'
CMD_LIGHT_ON = 'W'
CMD_LIGHT_OFF = 'w'

# ========= 介面風格 (Cyberpunk Theme) =========
# 顏色變數：
# 背景: #0f172a (深藍黑)
# 面板: #1e293b (稍淺的深藍灰)
# 邊框: #334155
# 亮點: #22d3ee (螢光青)
# 文字: #e2e8f0 (灰白)

DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #0f172a;
    color: #e2e8f0;
    font-family: "Segoe UI", "Consolas", sans-serif;
    font-size: 14px;
}

/* 標題欄 */
QLabel#HeaderTitle {
    color: #22d3ee;
    font-size: 24px;
    font-weight: bold;
    letter-spacing: 2px;
    border-bottom: 2px solid #22d3ee;
    padding-bottom: 5px;
}

QLabel#HeaderClock {
    color: #94a3b8;
    font-size: 16px;
    font-family: "Consolas";
}

/* 群組框 (Panel) */
QGroupBox {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    margin-top: 24px;
    font-weight: bold;
    color: #38bdf8;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 15px;
    padding: 0 5px;
    background-color: #0f172a; /* 讓標題背景與主背景融合 */
}

/* 按鈕 (科技感) */
QPushButton {
    background-color: #0f172a;
    border: 1px solid #38bdf8;
    color: #38bdf8;
    border-radius: 4px;
    padding: 8px;
    font-weight: bold;
    text-transform: uppercase;
}

QPushButton:hover {
    background-color: #38bdf8;
    color: #0f172a;
    box-shadow: 0 0 10px #38bdf8;
}

QPushButton:pressed {
    background-color: #0ea5e9;
    color: white;
    border: 1px solid #0ea5e9;
}

/* WASD 方向鍵專屬樣式 */
QPushButton#NavBtn {
    font-size: 22px;
    background-color: #1e293b;
    border: 2px solid #475569;
    color: #94a3b8;
    border-radius: 8px;
}
QPushButton#NavBtn:pressed {
    background-color: #22d3ee;
    color: #000;
    border-color: #22d3ee;
}

/* 輸入框 */
QLineEdit, QComboBox {
    background-color: #0f172a;
    border: 1px solid #475569;
    color: #fff;
    padding: 6px;
    border-radius: 4px;
}
QLineEdit:focus {
    border: 1px solid #22d3ee;
}

/* 影像區 (模擬 CRT 螢幕邊框) */
QLabel#VideoLabel {
    background-color: #000;
    border: 2px solid #22d3ee;
    border-radius: 4px;
}

/* Log區 */
QPlainTextEdit {
    background-color: #0a0a0a;
    border: 1px solid #333;
    color: #10b981; /* Matrix Green */
    font-family: "Consolas";
    font-size: 12px;
}

/* 進度條 */
QProgressBar {
    background-color: #0f172a;
    border: 1px solid #475569;
    border-radius: 4px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0ea5e9, stop:1 #22d3ee);
}
"""
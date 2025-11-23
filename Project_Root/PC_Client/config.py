import os

# ========= 參數設定 =========
# 專案路徑設定
SKETCH_DIR = "esp32s3_cam"          
SKETCH_NAME = "esp32s3_cam.ino"
SOURCE_INO = "code.ino"             

# Arduino CLI 編譯參數
FQBN = (
    "esp32:esp32:esp32s3:"
    "FlashSize=16M,"          
    "PSRAM=opi,"              
    "PartitionScheme=fatflash,"  
    "UploadSpeed=921600"      
)

# Serial 設定
BAUD_RATE = 115200                  
ESP32_URL = "https://espressif.github.io/arduino-esp32/package_esp32_index.json"

# 影像設定
DEFAULT_WIDTH = 640
DEFAULT_HEIGHT = 480

# 環境變數設定 (解決 Unicode 問題)
os.environ["PYTHONIOENCODING"] = "utf-8"
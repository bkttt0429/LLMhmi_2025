import os
import shutil
import time
import subprocess
import serial
from serial.tools import list_ports
import config  # 匯入設定檔

class SerialManager:
    def __init__(self):
        self.ser = None

    def get_ports(self):
        """取得可用 Port 列表"""
        return list_ports.comports()

    def connect(self, port):
        """連接 Serial"""
        self.disconnect()
        try:
            self.ser = serial.Serial(port, config.BAUD_RATE, timeout=0.1)
            return True, f"🔗 Serial 已連線: {port}"
        except Exception as e:
            return False, f"⚠️ 無法開啟 Serial: {e}"

    def disconnect(self):
        """斷開 Serial"""
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
                return True, "🔓 Serial Port 已釋放"
        except Exception as e:
            return False, f"⚠️ 關閉 Serial 錯誤: {e}"
        finally:
            self.ser = None

    def read_line(self):
        """讀取一行資料 (Non-blocking)"""
        if self.ser and self.ser.is_open and self.ser.in_waiting:
            try:
                return self.ser.readline().decode(errors="ignore").strip()
            except:
                pass
        return None

    def send_boot_signal(self, port):
        """發送強制 Boot 訊號"""
        self.disconnect()
        try:
            s = serial.Serial(port, config.BAUD_RATE)
            s.dtr = False; s.rts = False
            s.dtr = True; s.rts = False; time.sleep(0.1)
            s.rts = True; time.sleep(0.1)
            s.rts = False; time.sleep(0.2)
            s.dtr = False; s.close()
            return True, "✅ 強制 Boot 訊號已發送"
        except Exception as e:
            return False, f"⚠️ Boot 訊號發送失敗: {e}"

# === 燒錄相關獨立函式 ===
def prepare_sketch():
    if not os.path.exists(config.SOURCE_INO):
        return False, f"❌ 找不到 {config.SOURCE_INO}"
    if not os.path.exists(config.SKETCH_DIR):
        os.makedirs(config.SKETCH_DIR, exist_ok=True)
    dest_path = os.path.join(config.SKETCH_DIR, config.SKETCH_NAME)
    shutil.copy(config.SOURCE_INO, dest_path)
    return True, "✅ Sketch 準備完成"

def compile_and_upload(port, log_callback):
    """
    執行編譯與上傳
    log_callback: 一個函式，用來接收並顯示 Log
    """
    # 1. 檢查 Core
    log_callback("🔍 檢查 ESP32 核心...")
    check = subprocess.run(["arduino-cli", "core", "list"], capture_output=True, text=True, encoding="utf-8", errors="ignore")
    if "esp32:esp32" not in check.stdout:
        log_callback("⚠️ 安裝 ESP32 核心中...")
        subprocess.run(["arduino-cli", "core", "update-index", "--additional-urls", config.ESP32_URL])
        subprocess.run(["arduino-cli", "core", "install", "esp32:esp32", "--additional-urls", config.ESP32_URL])

    # 2. 編譯
    log_callback("=== Compile (編譯中)... ===")
    comp = subprocess.run(["arduino-cli", "compile", "--fqbn", config.FQBN, config.SKETCH_DIR, "--additional-urls", config.ESP32_URL], capture_output=True, text=True, encoding="utf-8", errors="ignore")
    if comp.returncode != 0:
        log_callback("❌ compile 失敗:\n" + comp.stderr)
        return False

    # 3. 上傳
    log_callback(f"=== Upload (上傳至 {port})... ===")
    upl = subprocess.run(
        ["arduino-cli", "upload", "-p", port, "--fqbn", config.FQBN, 
         "--upload-field", "upload.speed=115200", "--upload-field", "upload.flash_mode=dio", config.SKETCH_DIR],
        capture_output=True, text=True, encoding="utf-8", errors="ignore"
    )
    log_callback("upload output:\n" + upl.stdout)
    
    if upl.returncode != 0:
        log_callback("❌ upload 失敗:\n" + upl.stderr)
        return False
        
    log_callback("✅ Upload complete.")
    return True